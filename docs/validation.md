# Validation of v0.1.0

Local validation was performed on 2026-10-27 on macOS 27.0.1 arm64. The native
development build used Rust 1.95.0. The checks below establish correctness and
installability for the tested configurations; they are not evidence of sampling
quality, a speedup over other implementations, or reproduction of a paper.

## Correctness and contracts

The [Python tests](../tests/test_expander.py) contain 105 passing cases across the
Expander, Composite, and native boundary. They compare every pair of assignments
on every three-variable interaction graph in both SPIN and BINARY form against
an [independent exhaustive oracle](../tests/reference.py). Random five-variable
closures and a fixture requiring newly generated parents check iterative expansion.

Other checks cover pair-energy conservation, exact ground states, equal-energy
nonoptimal parents, zero and subnormal edges, mixed variable labels, offsets,
vartype conversion, input immutability, deduplication, empty and singleton cases,
budget precedence, deterministic replay, and more than 64 disagreement components.
Composite checks exercise the dimod contract, manual two-stage equivalence,
parameter collisions, future-backed responses, metadata, and child resource closure.
A subprocess test verifies GIL release and SIGINT propagation on POSIX systems;
that signal test is skipped on Windows.

Seven Rust tests pass, including deliberate hash collisions, capacity overflow,
input validation, interruption, and a bounded 130-component enumeration. The
allocation-failure checks use deterministic capacity overflow, not deliberate
system memory exhaustion.

The following development gates passed:

```sh
mise run check
mise run examples
mise run distribution
cargo +1.85.0 test --locked
cargo +1.85.0 check --locked --features python
```

`check` includes Rust tests, rustfmt, Clippy with warnings denied, Python tests,
and Ruff lint/format checks. Rust 1.85.0 passed both its tests and compilation of
the Python bindings. Both workflow files also passed actionlint 1.7.12 syntax
validation; this does not execute the hosted jobs.

## Installed distribution checks

The local artifacts are an abi3 macOS arm64 wheel and an sdist. The
[distribution verifier](../scripts/verify_distribution.py) checks metadata,
README rendering with `twine check --strict`, native extension presence, the MIT
license, typing files, and source inclusion. It rejects caches and generated
benchmark data. Each artifact is independently installed
in a new environment outside the checkout, where an import/API smoke check,
the full Python suite, and both public examples run against the installed package.

| Python | dimod | NumPy | Installation tested | Result |
| --- | --- | --- | --- | --- |
| 3.10.18 | 0.12.22 | 2.2.6 | Wheel and sdist | 105 passed each |
| 3.13.3 | 0.12.23 | 2.5.4 | Wheel and sdist | 105 passed each |
| 3.14.6 | 0.12.23 | 2.5.4 | Wheel and sdist | 105 passed each |
| 3.10.18 | 0.12.21 | 1.24.0 | Wheel, minimum declared dependencies | 105 passed |

With NumPy 2.5.4, seven upstream dimod deprecation warnings occur when it assigns
array shapes for empty sample sets. The tests pass, the warnings remain visible,
and no dependency code is patched or warning filter installed.

Local machine-readable evidence is saved in `dist/verification.json` and the
version-specific `dist/verification-py310.json`, `dist/verification-py314.json`,
and `dist/verification-minimum.json` reports. Reports identify the installed
versions, artifact SHA-256 values, and test output. Build outputs are ignored by
Git and are not included in published distributions.

## Workload measurements

The [runner](../benchmarks/run.py) measures six fixed input families in separate
processes. The saved manifest is `benchmarks/results/local.json`; the accompanying
`local-artifacts/` directory contains coefficients, initial states, outputs, and
energies. The manifest records source hashes, environment, seeds, budgets,
component counts, counters, timing phases, and peak process RSS. The checkout
had no commit yet; the manifest records a null commit and dirty state, with source
hashes identifying the measured implementation.

These are single local runs using Python 3.13.3, dimod 0.12.23, NumPy 2.5.4, and
the default finite budgets. RSS includes the interpreter, dependencies, and
workload preparation. Timing is wall time for the API call. These measurements
are not statistically estimated performance guarantees.

| Input family | Variables / edges | Initial / output rows | Time (ms) | Peak RSS (MB) | Stop reason |
| --- | --- | --- | --- | --- | --- |
| Small independent | 8 / 0 | 4 / 256 | 6.76 | 47.35 | `candidate_limit` |
| Wide independent | 128 / 0 | 16 / 10000 | 11.99 | 54.13 | `sample_limit` |
| Dimers | 128 / 64 | 32 / 10000 | 15.06 | 54.26 | `sample_limit` |
| Chain | 256 / 255 | 16 / 10000 | 31.33 | 59.51 | `sample_limit` |
| Sparse | 1024 / 1540 | 16 / 10000 | 144.43 | 90.93 | `sample_limit` |
| Dense | 128 / 2464 | 32 / 32 | 14.32 | 48.22 | `exhausted` |

The [verifier](../benchmarks/verify.py) successfully replayed all six saved inputs,
checking source/artifact hashes, output row order, unique assignments, energies,
and every nontiming statistic. The dense case demonstrates that expansion need
not add any rows. The small case reaches all 256 assignments but still stops on
its candidate budget while checking duplicates; discovering all states is not a
separate stopping rule.

```sh
uv run python benchmarks/verify.py benchmarks/results/local.json
```

The runner refuses to overwrite an existing report. For a fresh measurement,
select a new `--output` path and preserve its artifact directory with the report.

## Hosted validation and publication

CI is configured for Linux with Python 3.10 through 3.14, macOS and Windows with
Python 3.13, minimum dependency versions, and Rust 1.85. Hosted CI has not yet run
because this checkout has no Git remote or commits. Linux and Windows are
configured targets, not locally validated platforms. The release workflow builds
Linux x86_64, macOS arm64, and Windows x86_64 wheels, tests the installed wheels,
and builds and verifies the sdist.

No commit, tag, GitHub release, PyPI project, or publication was created during
local implementation. The remaining hosting/account steps and explicit publish
procedure are described in [Releasing](releasing.md).
