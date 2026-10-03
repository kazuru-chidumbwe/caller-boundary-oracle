# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

## [1.0.12] — 2026-09-08

### Changed

- Clean-provenance re-execution of the `v1.0.7` defect factorial and `v1.0.9` gmrtd `v1.1.3` remeasurement, plus the 3 gmrtd success-path-control FP cells. Fixes provenance defects in the `v1.0.7`/`v1.0.9` deposits (wrong-year `generated_at`, unreachable harness commit, absolute host paths). Scores identical to the historical deposits.
- **Zenodo DOI not yet minted for this tag.** GitHub→Zenodo webhook delivery for the release event returned 504 timeout on all attempts (initial + 4 redeliveries through 2026-09-08T11:17Z); author minting manually. See [`docs/ZENODO.md`](docs/ZENODO.md).

## [1.0.11] — 2026-09-05

### Changed

- Live **evidence** pin remains **`v1.0.9`** / Zenodo `10.5281/zenodo.22097289`. This tag archives tip metadata only.
- Tip Zenodo version DOI `10.5281/zenodo.22314067` (concept `10.5281/zenodo.22095366`) minted via GitHub→Zenodo for tag `v1.0.11`.

## [1.0.10] — 2026-08-25

### Changed

- Cite surfaces record minted Zenodo version DOI `10.5281/zenodo.22097289` (concept `10.5281/zenodo.22095366`) for tag `v1.0.9` (GitHub→Zenodo).
- Added [`docs/ZENODO.md`](docs/ZENODO.md). Live evidence pin remains **`v1.0.9`**.

## [1.0.9] — 2026-08-25

### Changed

- Cite-surface sync: `CITATION.cff`, `.zenodo.json`, `README.md`, and `docs/DISCLOSURE-AND-DATA-AVAILABILITY-2026-07-26.md` now declare live pin **`v1.0.9`**.
- DAS: PR #446 recorded as **merged** (`v1.1.3` / `1701e74`); remeasurement digest `04cdd3dd…` listed; Zenodo described as **pending** (GitHub Releases are the canonical deposits).
- `scripts/preflight_banned_terms.py`: skip self when scanning a tree that includes this script.

### Note

- Defect factorial deposit remains Release **`v1.0.7`**. Remeasurement bytes remain digest `04cdd3dd…` (asset also on `v1.0.8`).

## [1.0.8] — 2026-08-25

### Added

- Remeasurement of locked TC-AC-01 (gmrtd-only, 100 runs) against upstream `v1.1.3` (`64bd6ab`): baseline and mitigated each **50/50 Score 2** (fail-closed). Manifest SHA-256 `04cdd3dd61f983e90140cc2bc16913aa4f0f3fc5dd040cd271fd2f72387f93e3`.

### Changed

- `cmd/tc-ac-01`: `ReaderStatus` implements `Status(reader.Status)` for gmrtd ≥ typed-status API; gate accepts Score-0 silent path **or** Score-2 fail-closed path.
- Unit test expects fail-closed Score 2 under the remeasurement pin.
- Docs: dual gmrtd pins (defect `8fea245` / remeasurement `v1.1.3`).

### Note

- Historical 200-run defect factorial remains under tag `v1.0.7` + pin `8fea245` (digest `e15f4b57…`). Do not conflate the two pins.

## [1.0.7] — 2026-08-10

### Fixed (artifact / baseline review)

- Baseline gmrtd arm drives shipped `reader.ReadDocument` (not hand-composed DoPACE/DoBAC); `PaceSurfacedToCaller` measured from return error.
- Pin gmrtd to `8fea245` (release 0.45.0); bootstrap/paper verify; provenance `gmrtd_commit`.
- Drop vacuous wire N=100 → N=1 (deterministic simulator); shared observability vectors; `SOURCE_DATE_EPOCH`; fence TC-FI-01 / fail-closed pymrtd.

### Changed


## [1.0.6] — 2026-08-10

### Fixed

- `drivers/pymrtd-offline/run_smoke.py`: emit `variant` + `provenance` so offline PA smoke validates under `schemas/run-artifact-v1.json` (closes the last schema gap in the deposit).
- Success-path control: offline PA smoke runs **before** directory fingerprint.

### Added

- `scripts/package_locked_runs.sh` + `make package-locked-runs` — hard release gate (banned-term + abs-path + full run-artifact schema scan) → SemVer-named `emrtd-locked-runs-vX.Y.Z.zip`.

### Changed


## [1.0.5] — 2026-08-10

### Fixed

- Provenance: never emit empty `harness_commit` (Java exit-code check); 1-based `run_index` defaults; AA/CA scripts pass `-run-index`.
- Store `profile_path` relative to harness root (Go/Java/Python) so deposits do not embed host absolute paths.

### Changed

- Fresh lab regen on Lab Test Server (`4510c47` tip): primary AC-01 digest `c6f03d7e…`; success-path control `b98b354d…`.
- Option A is no longer a separate tree — tip uses JMRTD 0.8.6 only; cite the primary digest for the factorial.
- Locked-run deposit: Release `locked-runs-2026-08-10b` (zip `emrtd-locked-runs-2026-08-10b.zip`). Primary factorial schema-OK; offline-pa smoke under success-path still lacked provenance until `v1.0.6`.

## [1.0.4] — 2026-08-10

### Added

- `CITATION.cff` + `.zenodo.json` — author/ORCID/keywords for GitHub “Cite this repository” and Zenodo GitHub-integration metadata.
- `SECURITY.md` — harness vulnerability reporting channel; points to disclosure log for third-party library notices.
- Frozen JSON Schema files under `schemas/` with `verify_manifest.py` enforcement.
- CI on `main` / PRs; `scripts/preflight_banned_terms.py`.

### Changed

