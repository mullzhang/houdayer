# API

## HoudayerExpander

```python
HoudayerExpander().sample(
    bqm,
    *,
    initial_states=None,
    max_num_samples=10000,
    max_pairs=10000,
    max_candidates=100000,
    seed=None,
    include_initial_states=True,
    **kwargs,
)
```

The result is a `dimod.SampleSet`. `sample_ising()` and `sample_qubo()` use dimod's
standard mixins. `parameters` lists supported sample arguments; `properties`
identifies the algorithm and package version. Unknown keywords produce a
`SamplerUnknownArgWarning`, as required by dimod. `num_reads` is not an expansion
parameter.

| Argument | Contract |
| --- | --- |
| `bqm` | A `dimod.BinaryQuadraticModel`, SPIN or BINARY. All biases, the offset, and the sum of their absolute values must be finite. |
| `initial_states` | Required, nonempty `SampleSet` or dimod samples-like object. No random initialization. |
| `max_num_samples` | Positive integer; cap on the unique **internal pool**, including unique inputs even when they are omitted from output. |
| `max_pairs` | Nonnegative integer; cap on unordered parent pairs started, including a pair stopped partway through enumeration. |
| `max_candidates` | Nonnegative integer; cap on non-parent candidate assignments checked, including duplicates across pairs. |
| `seed` | Integer from 0 through `2**64 - 1`. `None` draws a seed with system entropy and records it for replay. |
| `include_initial_states` | Boolean. If false, return only assignments absent from the entire input pool. |

Limits must fit the platform's signed pointer-sized integer. Boolean values are
not accepted as integer limits or seeds. The product of the sample cap and the
variable count must fit addressable memory. This is not a promise that an
allocation of that size will succeed: the pool grows on demand and allocation
failures propagate as `MemoryError`.

### Input handling

Every row must contain exactly the BQM's variable set. Labels are aligned to
`bqm.variables` without comparison sorting, so mixed hashable label types work.
Raw samples use the BQM's value domain. A `SampleSet` with a different SPIN/BINARY
vartype is converted according to its explicit vartype. Values are checked before
integer conversion. Inputs and the BQM are never modified.

Stored input energies and measurement counts are not used to select parents.
Duplicate input assignments are collapsed in first-occurrence order. A single
unique input is a valid no-op. A zero-variable BQM with an empty assignment is
valid; an empty collection of assignments is an error.

A sample cap below the number of unique inputs is an error; inputs are never
silently truncated. A zero pair/candidate budget is a valid no-op. Removing
initial states may produce an empty result, retaining the variables and vartype.

### Output handling

Rows appear in discovery order: unique inputs first, then new assignments. The
record is not sorted by energy (dimod's display and `.data()` may sort it).
All energies are recomputed from the original BQM in float64, including its
offset. Every row has `num_occurrences=1`. No energy filter or ranking is applied.
Additional input row fields are omitted because they do not describe generated
solutions.

`info["houdayer"]` contains:

| Field | Meaning |
| --- | --- |
| `num_input_rows` | Number of input record rows, not the sum of occurrence counts. |
| `num_initial_states` | Unique input assignments. |
| `num_new_states` | Unique assignments added by expansion. |
| `num_output_rows` | Returned row count, after applying `include_initial_states`. |
| `num_pairs` | Parent pairs started. Each unordered pair is processed at most once. |
| `num_candidates` | Non-parent candidate assignments checked. |
| `num_duplicates` | Checked candidates already present in the pool. Input duplicates and skipped parents are excluded. |
| `num_rounds` | Rounds started; zero when expansion does not start. |
| `stop_reason` | One of the reasons below. |
| `max_num_samples`, `max_pairs`, `max_candidates` | Effective budgets. |
| `seed`, `include_initial_states`, `version` | Effective configuration and implementation version. |
| `timing` | Preparation, native execution including transfer, and result construction times in seconds. These measurements are not reproducible values. |

Stop reasons are `insufficient_unique_states`, `sample_limit`, `candidate_limit`,
`pair_limit`, and `exhausted`. A single unique state takes precedence over all
limits. During expansion the priority is sample cap, candidate cap, then pair
cap. The pair cap is checked between pairs; it does not stop the last permitted
pair before that pair's candidate enumeration. Hitting a cap exactly is reported
as a cap even if there would have been no further work. `exhausted` means every
pair in the reached closure was exhausted; it does not mean every BQM solution
or ground state was found.

`KeyboardInterrupt` propagates rather than returning a successful partial result.

## HoudayerComposite

```python
HoudayerComposite(child_sampler, *, expansion_parameters=None)
sampler.sample(bqm, **child_parameters)
```

The child must be a `dimod.Sampler`. Expansion settings are copied and validated
when constructing the composite. `initial_states` cannot be set in this mapping:
the child supplies them. Unknown mapping keys are errors. Omission uses the
Expander defaults; an omitted expansion seed is drawn afresh for each call.

Every sampling keyword is forwarded to the child, including a child parameter
whose name matches an expansion parameter. For example, the child's `seed` does
not affect the expansion seed. Expansion parameters are not accepted through a
second path in `sample()`.

The child is called exactly once. Its response is resolved before postprocessing.
An empty child response is an error. Child exceptions propagate. The child must
accept the supplied BQM, including any topology restrictions it imposes.

Child `info` is shallow-copied into `info["child_info"]`; nested objects retain
their identity but are not modified. Measurement counts and fields such as
`chain_break_fraction` are not attached to new rows. The result supports the same
contract as a direct Expander call. `close()` and the context-manager protocol
close the child through `dimod.ComposedSampler`.
