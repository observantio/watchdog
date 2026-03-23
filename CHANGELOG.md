# Changelog

All notable changes to this project will be documented in this file.

This changelog follows a simple human-first format and keeps entries focused on what changed, why it matters, and what to do next.

## [Unreleased]

### Added

- Added richer Grafana datasource management UX with a new **View Metrics** action that loads metric names per datasource tenant key and displays them in a scrollable table modal.
- Added datasource-delete safety checks that detect linked dashboards before deletion and show a focused warning state in the confirmation dialog.
- Added click-to-jump wizard steps in Alert Manager group/rule creation flows so users can move directly between setup stages.
- Added request cancellation and timeout handling in the frontend API client with endpoint-aware timeout defaults for Loki/Tempo, Resolver, and Grafana calls.
- Added request ID propagation (`X-Request-ID`) across backend middleware/proxy error paths for improved incident traceability.
- Added a centered dotted-dropzone upload UI for RCA YAML overrides, with clearer file-state feedback and one-click clear behavior.
- Added a final wave of focused backend coverage tests across auth, bootstrap, Grafana dashboard/service flows, and TTL cache concurrency/error branches.

### Changed

- Refined dark-mode UI contrast across cards, borders, separators, hover states, and key surfaces to improve readability while preserving a minimal technical aesthetic.
- Tightened light-theme contrast and border clarity, removed the bluish page gradient, and applied targeted darker card borders on Grafana content areas (excluding the main tab strip).
- Unified card spacing and border consistency in shared UI primitives and page-level cards, including the Users summary card and embedded log volume widgets.
- Updated page/header icon styling to follow theme text color for stronger visual consistency in light mode.
- Improved Loki log exploration UX with clearer result controls, stronger stream card readability, better pagination/status presentation, and cleaner display filtering behavior.
- Updated Alert Rule editing UX: metric scope now resolves by tenant key (not internal ID), metric scope is shown as a key tag, metric loading control is compact icon-only, and PromQL input uses a textarea that preserves indentation.
- Polished Grafana dashboard editor mode switching (Form/JSON) with cleaner icon-based tab visuals and improved active-state hierarchy.
- Stabilized `ThemeContext` provider values using memoized callbacks/objects to reduce avoidable rerenders in theme consumers.
- Updated `ErrorBoundary` to limit detailed stack disclosure to development mode while preserving safe recovery actions in production.
- Improved Alert Manager data loading behavior to support partial success and surface endpoint-specific failures instead of silently masking API errors.
- Hardened Loki query execution against stale in-flight responses by aborting superseded requests and ignoring obsolete results.
- Hardened Tempo query interactions with abortable in-flight search requests and stale-response guards to reduce race-condition UI states.
- Tightened API key security controls by requiring update-level permission for key visibility toggle actions.
- Standardized backend validation/internal error payload shape with stable `error_code` and request-id-aware responses.
- Improved API Keys table readability with stronger container borders, row/column separators, and expanded cell padding for clearer icon-labeled columns and actions.
- Removed border styling from auth entry cards (`Login` and OIDC callback) to match the cleaner sign-in visual direction.
- Updated OIDC callback success handling to perform a hard redirect refresh (`location.replace("/")`) after token completion.

### Fixed

- Fixed top-navigation tab selection styling consistency with clearer active underline behavior.
- Fixed datasource metric lookup to send the tenant key (`orgId`) expected by the backend API.
- Fixed several edge cases where API requests could hang indefinitely or race each other during rapid query/filter changes.
- Fixed residual auth-page card border visibility by explicitly overriding base card borders on sign-in screens.

## [v0.0.1] - 2026-03-20

### Added

- Introduced a production release flow that ships deployable assets as GitHub Release attachments.
- Added `docker-compose.prod.yml` for image-based deployment (no local source build required).
- Added a release installer script (`release/install.sh`) so users can run the orchestration
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

Please use the development guide at `DEPLOYMENT.md` on how to deploy this on cloud service or local node

### Notes

- `notifier` and `resolver` are expected to publish their own images from their own repositories using matching version tags.
- Before tagging this repo, update `release/versions.json` so bundle and service versions reflect the intended release.
