# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-11-04

### Fixed

- README images and links use absolute URLs so they render on PyPI.

## [0.2.0] - 2026-11-04

### Added

- `pixgen optimize` command for local image optimisation with Pillow: profiles, dry-run,
  pixel-mode conversion, resizing, and output naming based on the target format.
- `--verbose` flag (`-vv` for tracebacks) with logging for unexpected and provider failures.
- Configurable provider request retries.
- Portable Pixgen CLI agent skill, with installation instructions.
- Documentation for image optimisation and the release process.

### Changed

- Provider-native CLI commands now live in `cli/`, keeping `providers/` CLI-agnostic.
- Native OpenAI, Gemini and OpenRouter CLI builders are merged into one.
- Model selection and parameter resolution are normalised across providers.
- Exit status is derived from per-result outcome counts.
- Provider clients are closed after each run.

### Fixed

- Root CLI help and model tree output.
- Optimisation sizing and encoding preflight checks.
- Output symlinks at the leaf path are rejected before resolution.
- AVIF artifact suffix is pinned.

## [0.1.1] - 2026-10-07

### Added

- OpenRouter as a built-in image provider, with nested model slugs.
- `pixgen info` command showing version and environment details.
- Model groups, with fuzzy interactive selection and group listing.
- CI and release workflows publishing to PyPI via trusted publishing.

### Fixed

- An unrelated `.env` file no longer crashes pixgen; credential sources are clarified.
- Help is shown when no command is given.
- Artifact output suffix follows the media type.

[0.2.1]: https://github.com/difegam/pixgen/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/difegam/pixgen/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/difegam/pixgen/releases/tag/v0.1.1
