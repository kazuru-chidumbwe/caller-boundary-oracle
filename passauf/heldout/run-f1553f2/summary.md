<!-- artifact_version=1 suite=heldout-passauf commit=f1553f28193a47ac5cef9cfe15869f8ed7368eb8 -->
| cell | library | variant | N | silent | status-only | surfaced | n/a | invalid | classes | ≥95% |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CELL-CTRL-bac-only-passauf-default | passauf | default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-CTRL-pace-proprietary-params-passauf-default | passauf | default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-PACE-passauf-default | passauf | default | 32 | 1 | 25 | 6 | 0 | 0 | 5 | no |
| CELL-VSC-PACE-passauf-default | passauf | default | 12 | 0 | 12 | 0 | 0 | 0 | 5 | yes |
| CELL-VSC-pace-success-multi-info-passauf-default | passauf | default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-pace-success-passauf-default | passauf | default | 101 | 0 | 0 | 0 | 101 | 0 | 1 | n/a |

Canonical manifest: `artifact-manifest.json` · commit `f1553f28193a47ac5cef9cfe15869f8ed7368eb8`

In-process simulators are deterministic (no RNG, no concurrency). Each profile is therefore run at N=1; multi-profile cells (e.g. the 50-profile AC-01 sweep) establish consistency across profiles, not repeated identical trials. The ≥95% finding threshold applies only to multi-profile cells (n ≥ 2); single-profile cells are reported with the threshold marked not applicable.
