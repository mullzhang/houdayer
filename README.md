# houdayer

Expand existing Ising or QUBO sample sets with Houdayer cluster recombination.
`HoudayerExpander` returns a `dimod.SampleSet`; `HoudayerComposite` adds the same
postprocessing to an existing dimod sampler. A Rust core performs component
discovery, bounded candidate enumeration, deduplication, and iterative expansion.

## Installation

Add the package to your uv project directly from GitHub. Building from source
requires Python 3.10 or newer and Rust 1.85 or newer:

```sh
uv add git+https://github.com/mullzhang/houdayer.git
```

Prebuilt wheels do not require Rust. The distribution name and import name are
both `houdayer`. See [release instructions](docs/releasing.md) for building and
publishing distributions.

## Expand an existing sample set

```python
import dimod
from houdayer import HoudayerExpander

bqm = dimod.BinaryQuadraticModel.from_ising({"a": 0, "b": 0}, {})
seeds = [{"a": -1, "b": -1}, {"a": 1, "b": 1}]
expanded = HoudayerExpander().sample(bqm, initial_states=seeds, seed=42)
assert len(expanded) == 4
print(expanded.info["houdayer"])
```

Use `initial_states` for an existing `SampleSet` or another dimod samples-like
object. Initial states are required; initial samples are never generated
automatically. The default budgets are 10,000 unique samples, 10,000 parent pairs, and 100,000 candidate
checks. Every call stops when a budget is reached or all reachable pairs have
been processed. Budgets can also end the enumeration of a single pair.

## Add postprocessing to a sampler

```python
import dimod
from houdayer import HoudayerComposite

sampler = HoudayerComposite(
    dimod.RandomSampler(),
    expansion_parameters={"max_num_samples": 1000, "seed": 42},
)
expanded = sampler.sample(bqm, num_reads=20, seed=7)
```

Constructor options control expansion. The arguments to `sample()` go to the
child, so its `seed` and any other options cannot collide with expansion options.
The composite supports the standard dimod context-manager/`close()` protocol.

## Interpretation

- Outputs are unique assignments, each with `num_occurrences=1`. They are not
  additional hardware measurements or independent samples from a target distribution.
- A cluster exchange preserves the **sum of the energies of complementary
  offspring**. Individual energies can change, even for equal-energy parents.
  If both parents are exact ground states, both offspring remain ground states.
- Initial samples are included by default, so the best returned energy cannot
  be worse than the best input energy. Other returned samples may have higher energy.
- No energy filtering, constraint repair, or local search is performed.
- Complete ground-state coverage, a diversity increase, and uniform sampling
  are not guaranteed. Budgets bound work, not a requested output count.

See [API semantics](docs/api.md), [algorithm and guarantees](docs/algorithm.md),
[development](docs/development.md), and [validation](docs/validation.md).

## References

- J. Houdayer, [A cluster Monte Carlo algorithm for 2-dimensional spin glasses](https://doi.org/10.1007/PL00011151) (2001).
- A. Vandenbroucque, E. I. Rodríguez Chiacchio, E. Munro,
  [The Houdayer Algorithm: Overview, Extensions, and Applications](https://arxiv.org/abs/2211.11556) (2022).
- A. J. Ochoa, M. J. A. Schuetz, H. G. Katzgraber,
  [Efficient Ground-State Manifold Amplification for Rydberg Atom Arrays via Houdayer Cluster Updates](https://arxiv.org/abs/2610.28528v2) (2026).

The implementation expands general BQMs over successive rounds. It does not
reproduce the MIS-specific pairing, repair, or stopping rules of the 2026 paper.

Licensed under the [MIT License](LICENSE).
