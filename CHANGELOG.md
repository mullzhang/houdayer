# Changelog

## 0.1.0

- Add `HoudayerExpander` for SPIN/BINARY BQMs and existing dimod samples.
- Add `HoudayerComposite` with separate child and expansion configuration.
- Implement iterative pool expansion in Rust, with streaming Gray-code
  enumeration, collision-safe deduplication, finite budgets, seeded traversal,
  signal handling, and execution statistics.
- Preserve arbitrary variable labels, offsets, and first-discovery output order.
- Add exhaustive-oracle tests, isolated distribution verification, examples,
  benchmark artifacts and replay verification, CI, and an opt-in release workflow.
