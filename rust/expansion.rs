//! Round-based pair traversal and streaming Gray-code enumeration.

use std::collections::TryReserveError;

use rand::{Rng, SeedableRng, seq::SliceRandom};
use rand_chacha::ChaCha8Rng;

use crate::{Graph, cluster::ClusterWorkspace, pool::Pool};

#[derive(Debug)]
pub enum RunError<E> {
    InvalidInput(&'static str),
    SizeOverflow,
    Allocation(TryReserveError),
    Interrupted(E),
}

impl<E> From<TryReserveError> for RunError<E> {
    fn from(error: TryReserveError) -> Self {
        Self::Allocation(error)
    }
}

#[derive(Clone, Debug)]
pub struct Config {
    pub max_num_samples: usize,
    pub max_pairs: usize,
    pub max_candidates: usize,
    pub seed: u64,
    pub include_initial_states: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopReason {
    InsufficientUniqueStates,
    SampleLimit,
    CandidateLimit,
    PairLimit,
    Exhausted,
}

impl StopReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::InsufficientUniqueStates => "insufficient_unique_states",
            Self::SampleLimit => "sample_limit",
            Self::CandidateLimit => "candidate_limit",
            Self::PairLimit => "pair_limit",
            Self::Exhausted => "exhausted",
        }
    }
}

#[derive(Debug, Default)]
pub struct Stats {
    pub num_input_rows: usize,
    pub num_initial_states: usize,
    pub num_new_states: usize,
    pub num_output_rows: usize,
    pub num_pairs: usize,
    pub num_candidates: usize,
    pub num_duplicates: usize,
    pub num_rounds: usize,
}

#[derive(Debug)]
pub struct Output {
    pub samples: Vec<i8>,
    pub stats: Stats,
    pub stop_reason: StopReason,
}

fn limit(pool: &Pool, stats: &Stats, config: &Config, between_pairs: bool) -> Option<StopReason> {
    if pool.rows.len() >= config.max_num_samples {
        Some(StopReason::SampleLimit)
    } else if stats.num_candidates >= config.max_candidates {
        Some(StopReason::CandidateLimit)
    } else if between_pairs && stats.num_pairs >= config.max_pairs {
        Some(StopReason::PairLimit)
    } else {
        None
    }
}

fn enumerate_pair<E>(
    workspace: &ClusterWorkspace,
    parent: usize,
    pool: &mut Pool,
    stats: &mut Stats,
    config: &Config,
    rng: &mut ChaCha8Rng,
    check_interrupt: &mut impl FnMut() -> Result<(), E>,
) -> Result<Option<StopReason>, RunError<E>> {
    let count = workspace.len();
    if count < 2 {
        return Ok(None);
    }
    let mut order = Vec::new();
    order.try_reserve_exact(count)?;
    order.extend(0..count);
    order.shuffle(rng);
    let mut counter = Vec::new();
    counter.try_reserve_exact(count)?;
    counter.resize(count, false);
    let mut swapped = Vec::new();
    swapped.try_reserve_exact(count)?;
    swapped.resize(count, false);
    let mut candidate = Vec::new();
    candidate.try_reserve_exact(pool.rows[parent].len())?;
    candidate.extend_from_slice(&pool.rows[parent]);
    let mut num_swapped = 0;
    let mut work = 0;

    loop {
        // A binary counter of arbitrary width drives a Gray-code traversal.
        // Only the component at the first zero bit changes. No 2**count integer is needed.
        let mut bit = 0;
        while bit < count && counter[bit] {
            counter[bit] = false;
            bit += 1;
        }
        if bit == count {
            return Ok(None);
        }
        counter[bit] = true;
        swapped[bit] = !swapped[bit];
        if swapped[bit] {
            num_swapped += 1;
        } else {
            num_swapped -= 1;
        }
        for &site in workspace.component(order[bit]) {
            candidate[site] = -candidate[site];
            work += 1;
            if work == 4096 {
                check_interrupt().map_err(RunError::Interrupted)?;
                work = 0;
            }
        }
        if num_swapped == count {
            // The other original parent is already in the pool.
            continue;
        }
        stats.num_candidates += 1;
        if !pool.insert(&candidate)? {
            stats.num_duplicates += 1;
        }
        if let Some(reason) = limit(pool, stats, config, false) {
            return Ok(Some(reason));
        }
    }
}

/// Expand a row-major SPIN buffer. Only rows present at a round's start become parents.
pub fn expand<E>(
    graph: &Graph,
    samples: &[i8],
    num_rows: usize,
    config: &Config,
    mut check_interrupt: impl FnMut() -> Result<(), E>,
) -> Result<Output, RunError<E>> {
    let n = graph.len();
    if num_rows == 0 || config.max_num_samples == 0 {
        return Err(RunError::InvalidInput(
            "initial states and max_num_samples must be nonempty",
        ));
    }
    if num_rows.checked_mul(n).ok_or(RunError::SizeOverflow)? != samples.len() {
        return Err(RunError::InvalidInput(
            "initial state shape does not match the graph",
        ));
    }
    let max_size = config
        .max_num_samples
        .checked_mul(n)
        .ok_or(RunError::SizeOverflow)?;
    if max_size > isize::MAX as usize {
        return Err(RunError::SizeOverflow);
    }
    let mut pool = Pool::default();
    for row in 0..num_rows {
        check_interrupt().map_err(RunError::Interrupted)?;
        let state = &samples[row * n..(row + 1) * n];
        if state.iter().any(|&s| s != -1 && s != 1) {
            return Err(RunError::InvalidInput(
                "initial state values must be -1 or +1",
            ));
        }
        pool.insert(state)?;
        if pool.rows.len() > config.max_num_samples {
            return Err(RunError::InvalidInput(
                "max_num_samples is smaller than the initial unique set",
            ));
        }
    }
    let mut stats = Stats {
        num_input_rows: num_rows,
        num_initial_states: pool.rows.len(),
        ..Stats::default()
    };
    let reason = if pool.rows.len() < 2 {
        StopReason::InsufficientUniqueStates
    } else if let Some(reason) = limit(&pool, &stats, config, true) {
        reason
    } else {
        let mut workspace = ClusterWorkspace::new(n)?;
        let mut rng = ChaCha8Rng::seed_from_u64(config.seed);
        let mut previous_end = 0;
        let mut order = Vec::new();
        'rounds: loop {
            let round_end = pool.rows.len();
            stats.num_rounds += 1;
            order.clear();
            order.try_reserve(round_end - previous_end)?;
            order.extend(previous_end..round_end);
            order.shuffle(&mut rng);
            for &right in &order {
                if right == 0 {
                    continue;
                }
                // A cyclic offset randomizes traversal without allocating all pairs.
                let mut left = rng.random_range(0..right);
                for _ in 0..right {
                    check_interrupt().map_err(RunError::Interrupted)?;
                    stats.num_pairs += 1;
                    workspace.find(
                        graph,
                        &pool.rows[left],
                        &pool.rows[right],
                        &mut check_interrupt,
                    )?;
                    if let Some(reason) = enumerate_pair(
                        &workspace,
                        left,
                        &mut pool,
                        &mut stats,
                        config,
                        &mut rng,
                        &mut check_interrupt,
                    )? {
                        break 'rounds reason;
                    }
                    if let Some(reason) = limit(&pool, &stats, config, true) {
                        break 'rounds reason;
                    }
                    left += 1;
                    if left == right {
                        left = 0;
                    }
                }
            }
            if pool.rows.len() == round_end {
                break StopReason::Exhausted;
            }
            previous_end = round_end;
        }
    };

    stats.num_new_states = pool.rows.len() - stats.num_initial_states;
    let first = if config.include_initial_states {
        0
    } else {
        stats.num_initial_states
    };
    stats.num_output_rows = pool.rows.len() - first;
    let output_size = stats
        .num_output_rows
        .checked_mul(n)
        .ok_or(RunError::SizeOverflow)?;
    let mut samples = Vec::new();
    samples.try_reserve_exact(output_size)?;
    for row in pool.rows.into_iter().skip(first) {
        check_interrupt().map_err(RunError::Interrupted)?;
        samples.extend_from_slice(&row);
    }
    Ok(Output {
        samples,
        stats,
        stop_reason: reason,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> Config {
        Config {
            max_num_samples: 1000,
            max_pairs: 10000,
            max_candidates: 100000,
            seed: 42,
            include_initial_states: true,
        }
    }

    #[test]
    fn all_independent_spin_assignments_are_recovered() {
        let graph = Graph::new::<()>(4, &[]).unwrap();
        let output = expand(&graph, &[-1, -1, -1, -1, 1, 1, 1, 1], 2, &config(), || {
            Ok::<(), ()>(())
        })
        .unwrap();
        assert_eq!(output.stats.num_output_rows, 16);
        assert_eq!(output.stats.num_pairs, 16 * 15 / 2);
        assert_eq!(output.stop_reason, StopReason::Exhausted);
    }

    #[test]
    fn huge_component_counts_stop_without_exponential_allocation() {
        let graph = Graph::new::<()>(130, &[]).unwrap();
        let samples = [vec![-1; 130], vec![1; 130]].concat();
        let mut config = config();
        config.max_candidates = 7;
        let output = expand(&graph, &samples, 2, &config, || Ok::<(), ()>(())).unwrap();
        assert_eq!(output.stats.num_candidates, 7);
        assert_eq!(output.stats.num_output_rows, 9);
        assert_eq!(output.stop_reason, StopReason::CandidateLimit);
    }

    #[test]
    fn interruption_is_not_a_successful_partial_result() {
        let graph = Graph::new::<&str>(4, &[]).unwrap();
        let error = expand(&graph, &[-1; 8], 2, &config(), || Err("cancelled")).unwrap_err();
        assert!(matches!(error, RunError::Interrupted("cancelled")));
    }

    #[test]
    fn capacity_overflow_is_recoverable() {
        let error = Graph::new::<()>(usize::MAX, &[]).unwrap_err();
        assert!(matches!(error, RunError::Allocation(_)));
        let graph = Graph::new::<()>(2, &[]).unwrap();
        let mut config = config();
        config.max_num_samples = usize::MAX;
        assert!(matches!(
            expand(&graph, &[-1, 1], 1, &config, || Ok::<(), ()>(())),
            Err(RunError::SizeOverflow)
        ));
    }

    #[test]
    fn input_invariants_are_checked_at_the_native_boundary() {
        assert!(Graph::new::<()>(2, &[(0, 2)]).is_err());
        assert!(Graph::new::<()>(2, &[(1, 1)]).is_err());
        let graph = Graph::new::<()>(2, &[]).unwrap();
        assert!(expand(&graph, &[0, 1], 1, &config(), || Ok::<(), ()>(())).is_err());
        assert!(expand(&graph, &[-1], 1, &config(), || Ok::<(), ()>(())).is_err());
        assert!(expand(&graph, &[], 0, &config(), || Ok::<(), ()>(())).is_err());
    }

    #[test]
    fn empty_model_keeps_one_empty_assignment() {
        let graph = Graph::new::<()>(0, &[]).unwrap();
        let output = expand(&graph, &[], 3, &config(), || Ok::<(), ()>(())).unwrap();
        assert_eq!(output.stats.num_output_rows, 1);
        assert_eq!(output.stats.num_initial_states, 1);
        assert_eq!(output.stop_reason, StopReason::InsufficientUniqueStates);
    }
}
