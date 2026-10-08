# WebAuthn held-out evaluation: design (8 October 2026, before any held-out run)

The cases and releases below have never been run against any library. Expectations are derived from each release's source, written to `webauthn/heldout/expectations.json` with the source reason per entry, and committed before the single evaluation run. The oracle (`classifier/observability.py`) and the status-field rule (`webauthn/STATUS-SIGNALS.md`) are used unchanged.

## New fault cases

Steps refer to W3C Web Authentication Level 3, Recommendation of 25 August 2026, sections 7.1 and 7.2.

| ID | Ceremony | Fault | Step |
| --- | --- | --- | --- |
| R-UPUV | registration | UP clear while UV is set | 7.1 step 15 |
| A-UPUV | authentication | UP clear while UV is set | 7.2 step 16 |
| R-ORIGPORT | registration | origin is the RP origin with port 8443 | 7.1 step 9 |
| A-ORIGPORT | authentication | origin is the RP origin with port 8443 | 7.2 step 12 |
| R-XORIG | registration | `crossOrigin: true`; the RP does not expect a cross-origin iframe | 7.1 step 10 |
| A-XORIG | authentication | `crossOrigin: true`; the RP does not expect a cross-origin iframe | 7.2 step 13 |
| R-NONESTMT | registration | `fmt` is `none` with a non-empty attestation statement | 7.1 step 22 (the none format requires an empty statement) |
| R-ALG | registration | the RP's `pubKeyCredParams` lists only RS256 (-257); the credential key is ES256 | 7.1 step 20 |
| A-UH | authentication | `userHandle` is another user's handle | 7.2 step 6 |
| A-CRED | authentication | the credential ID is not in `allowCredentials` | 7.2 step 5 |
| A-CNTEQ | authentication | `signCount` equal to the stored nonzero count | 7.2 step 23 (policy, as A-CNT) |

The 17 development cases and the three positive controls are run in the same evaluation, so every release has a full matrix; the pre-registered claim covers every (release, case) pair not run during development.

## Releases

Rule, fixed now: for each library, the pinned release, plus the newest release of the preceding major line (for 0.x versions, the preceding minor line), plus Fido2 5.0.0-preview.7 (the first line with the Level 3 backup-state check). A release whose API the unchanged driver cannot call is recorded as not built, as in the gmrtd sweep. Releases are resolved from the package registries on the day of the run and recorded with their artifact hashes.

## Driver change before the run

Drivers read `pubKeyCredParams` from `options.json` instead of fixing ES256 (needed for R-ALG). This change is made and committed before expectations are written.
