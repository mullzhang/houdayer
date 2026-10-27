# Development

Use English for all version-controlled content.
Python provides the dimod boundary; Rust owns graph traversal, enumeration,
deduplication, and termination. The Python oracle in `tests/reference.py` is only
for exhaustive tests, never a runtime fallback.

Use the versions in `mise.toml` and the checked-in Cargo/uv lockfiles:

```sh
mise install
mise run setup
mise run check
mise run examples
mise run distribution
```

Equivalent individual commands are available in `mise.toml`. Python 3.10+ is
supported for consumers; development is pinned to Python 3.13.3. Rust 1.85+ is
required for source builds. Prebuilt abi3 wheels support CPython 3.10+ on their
platform. Free-threaded Python and PyPy are not currently included in the wheel
matrix.

`uv sync` rebuilds the editable extension when Python/Rust inputs change.
`cargo test --locked` tests the core without Python; Clippy uses the `python`
feature to inspect the bindings as well. Build release distributions with
`uv build --no-sources`, which builds the wheel from the sdist.

Run reproducible benchmarks on macOS or Linux:

```sh
mise run benchmark
uv run python benchmarks/verify.py benchmarks/results/local.json
```

The runner stores inputs, outputs, coefficients, counters, timings, peak process
RSS, package versions, source fingerprints, and seeds. Each case runs in a fresh
process. RSS includes the interpreter and dependencies. Timings are measurements
of these specific workloads, not general performance claims. Generated artifacts
are ignored by Git; preserve the JSON and its artifact directory together when
sharing results.
