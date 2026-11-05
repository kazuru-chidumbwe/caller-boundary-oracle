<!-- artifact_version=1 suite=u6-jmrtd commit=b82b3d8fb63ea0f926e13ebd8c4b7912ff0a459e -->
| cell | library | variant | N | silent | status-only | surfaced | n/a | invalid | classes | ≥95% |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CELL-VSC-PACE-GA4BODY-jmrtd-catch-continue | jmrtd | catch-continue | 4 | 2 | 0 | 2 | 0 | 0 | 2 | no |
| CELL-VSC-PACE-GA4BODY-jmrtd-propagate | jmrtd | propagate | 4 | 2 | 0 | 2 | 0 | 0 | 2 | no |
| CELL-VSC-pace-success-jmrtd-catch-continue | jmrtd | catch-continue | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-pace-success-jmrtd-propagate | jmrtd | propagate | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |

Canonical manifest: `artifact-manifest.json` · commit `b82b3d8fb63ea0f926e13ebd8c4b7912ff0a459e`

In-process simulators are deterministic (no RNG, no concurrency). Each profile is therefore run at N=1; multi-profile cells (e.g. the 50-profile AC-01 sweep) establish consistency across profiles, not repeated identical trials. The ≥95% finding threshold applies only to multi-profile cells (n ≥ 2); single-profile cells are reported with the threshold marked not applicable.
