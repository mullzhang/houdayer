# Algorithm and guarantees

For two assignments, construct the set of variables on which they disagree.
The connected components of the BQM interaction graph induced by these variables
are the exchangeable clusters. A candidate chooses one parent's assignment on
each entire component and retains the agreement variables.

## Topology and energy

Only exactly nonzero quadratic biases define edges. Tiny nonzero coefficients
are retained. The same topology is valid for BINARY and SPIN models: Python maps
sample values to -1/+1 for the core, without numerically rescaling biases. This
also avoids losing subnormal edges during a BINARY-to-SPIN coefficient conversion.
The native core needs no energy coefficients; returned energies are evaluated
using the original BQM.

Complementary offspring satisfy

```text
E(s') + E(t') = E(s) + E(t).
```

Internal edges retain their pair contribution; boundary edges meet agreement
variables and their changes cancel between the two offspring. Linear terms
cancel in the same way. The two constant terms remain unchanged. This establishes
the invariant for general finite BQMs; see [Lemma IV.1 of the generalized
Houdayer paper](https://arxiv.org/html/2211.11556v1).

Equal-energy parents need not have individually equal-energy offspring. For
`E(s) = s[0] + s[1]`, parents `(1, -1)` and `(-1, 1)` have energy zero, but
offspring `(1, 1)` and `(-1, -1)` have energies 2 and -2. Zero explicit fields
alone do not establish individual preservation either: agreement variables can
create nonzero boundary contributions. If both parents are exact global minima,
neither child can fall below that minimum and their fixed sum forces both to
remain minima.

## Bounded enumeration

With `c` disagreement components there are `2**c` assignments, including the two
parents when `c > 0`. The engine skips the parents and streams the other
assignments once using Gray code. It uses a variable-width counter, so `c` is not
restricted to the width of an integer. Only one component changes per Gray-code
step. No array of all masks is allocated. For `c <= 1` no candidates are needed.

The pool stores each assignment once. A hash maps to row indices, with full-row
comparison to resolve collisions. Hash-table iteration order never determines
traversal or output order. Native allocations use fallible reservations where
the engine grows buffers and map allocation failures to Python exceptions.

Parent rows are immutable. Each round fixes its available parent set. If the
previous round ended at index `p` and the current pool has `m` rows, the next
round visits right endpoints `p..m`; for each right endpoint `j`, left endpoints
range over `0..j`. Thus every unordered parent pair is visited once, with new
rows becoming eligible in the next round, without storing a quadratic pair list.

ChaCha8 seeded by the recorded 64-bit seed shuffles right endpoints, selects a
cyclic starting left endpoint for each, and shuffles each pair's component order.
These choices influence results under a finite budget. The Gray-code sequence
then remains deterministic. Native computation is single-threaded, with the GIL
released and periodic signal checks.

The per-pair component search takes O(n + m) work in the worst case. A candidate
requires row hashing and potentially a stored row copy, so O(n) work remains
even when one small component changes. Storage scales with the retained sample
pool, graph, and reusable traversal buffers, not all possible pairs or masks.
The sample count cap is not a byte-memory cap; choose it with the variable count
and available memory in mind. The returned NumPy buffer temporarily coexists
with the pool while results are transferred.

## Scope of the guarantees

Within the same implementation version, input column/row order, configuration,
and seed, outputs and counters are reproducible. Timings are excluded. No
cross-version or cross-platform bitwise reproducibility promise is made.

Variables identical across every initial assignment cannot change. A connected
disagreement region only exchanges the two parents. Consequently the reachable
closure can be much smaller than the full solution space, even with large
budgets. Recombination does not promise independent or uniformly distributed
samples, more unique solutions, complete ground-state coverage, or feasibility
of constraints that have been encoded in a BQM.

The implementation is an iterative general-BQM expander. The [2026 MIS
paper](https://arxiv.org/html/2610.28528v2) fixes seed pairs within a pass and
includes MIS repair and different stopping rules. Those experiment-specific
features are not implemented here. This package makes no claim of reproducing
that paper's amplification factors.
