# Changelog

All notable changes to this project will be documented in this file.

This changelog follows a simple human-first format and keeps entries focused on what changed, why it matters, and what to do next.

## [Unreleased]

## [v0.0.1] - 2026-03-20

### Added

- Introduced a production release flow that ships deployable assets as GitHub Release attachments.
- Added `docker-compose.prod.yml` for image-based deployment (no local source build required).
- Added a release installer script (`release/install.sh`) so users can extract the release tarball and bootstrap quickly.
- Added `release/versions.json` as the central version manifest for independent per-service image tags.
- Added release packaging for architecture-specific bundles (`amd64`, `arm64`, and `multi` metadata bundle).

### Changed

- Updated `.env.example` to include stronger, meaningful default placeholder values and clearer production-oriented defaults.
- Switched production image versioning from one shared image tag to per-service tags:
  - `IMAGE_TAG_WATCHDOG`
  - `IMAGE_TAG_GATEKEEPER`
  - `IMAGE_TAG_UI`
  - `IMAGE_TAG_OTEL_AGENT`
  - `IMAGE_TAG_NOTIFIER`
  - `IMAGE_TAG_RESOLVER`
- Updated root release workflow to read versions from `release/versions.json`, publish local service images, and build release bundles pinned to the manifest values.

### Notes

- `notifier` and `resolver` are expected to publish their own images from their own repositories using matching version tags.
- Before tagging this repo, update `release/versions.json` so bundle and service versions reflect the intended release.
