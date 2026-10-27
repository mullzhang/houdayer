# Development rules

- Use English for all version-controlled content.
- Keep public Python APIs compatible with dimod. Keep native implementation details private.
- Preserve the pair-energy invariant; do not claim individual energy preservation for arbitrary parents.
- Keep enumeration bounded and lazy. Never allocate all cluster masks or all parent pairs.
- Validate changes with `mise run check`, `mise run examples`, and `mise run distribution` as appropriate.
- Keep build artifacts out of source distributions.
- Do not commit, push, or publish unless explicitly requested.
