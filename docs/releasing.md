# Releasing

This repository builds the `houdayer` Python distribution with an abi3 native
extension. A release consists of platform wheels and a source archive. The Rust
crate is an internal implementation and is not published separately to crates.io.

## Local release verification

1. Update the version in `pyproject.toml` and `Cargo.toml`, update both lockfiles,
   and add the release notes to `CHANGELOG.md`.
2. Run `mise run check`, `mise run examples`, and `mise run distribution`.
3. Inspect `dist/verification.json`. The verifier checks archive contents, metadata,
   README rendering, license inclusion, and isolated installation of both the
   wheel and sdist, then runs the full Python test suite and both public examples
   from outside the checkout.
4. Review the supported-platform CI results. A local macOS run does not prove
   Linux or Windows behavior.
5. Check that the PyPI project name is available or owned by the release account.
   The PyPI JSON endpoint returned HTTP 404 on 2026-10-27; that does not reserve
   the name or establish that PyPI will permit its registration.

Caches, benchmarks' generated outputs, local virtual environments,
and credentials must not appear in published archives. The build configuration
uses an explicit source allowlist, and the verifier rejects excluded paths.
Do not strip the macOS extension: the release profile preserves the native
linker's symbol layout.

## GitHub and PyPI configuration

Push the reviewed repository to `mullzhang/houdayer` and run CI before a public
release. Configure a protected GitHub environment named `pypi` and a PyPI Trusted
Publisher for this repository's `release.yml` workflow and that environment.
For a new PyPI project, use a pending publisher if the account supports it.
These are account/hosting steps, not changes made by installing the package.

The release workflow builds Linux x86_64, macOS arm64, and Windows x86_64 wheels
and one sdist. It uploads build artifacts for review. Publishing is disabled by
default. To publish, run the workflow manually on a matching `v<version>` tag
with `publish` enabled, after the release checks and environment approval.
The publishing job requires that tag to match the built package version and uses
OIDC instead of a stored API token.

Other supported source-build platforms can use the sdist. Add additional wheel
targets only together with installation tests for those targets. Creating a tag,
GitHub release, PyPI project, or publishing an artifact is an explicit release
action; local verification does not perform any of them.
