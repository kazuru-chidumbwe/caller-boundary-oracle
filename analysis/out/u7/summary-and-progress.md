<!-- artifact_version=1 suite=u7-bac commit=be99fefd61a5fdf2e7b86a70337a900924d97b76 -->
| cell | library | variant | N | silent | status-only | surfaced | n/a | invalid | classes | ≥95% |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CELL-VSC-bac-only-success-dmrtd-default | dmrtd | default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-emrtd-dotnet-default | emrtd-dotnet | default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-64bd6ab-allow-fallback | gmrtd | 64bd6ab-allow-fallback | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-64bd6ab-default | gmrtd | 64bd6ab-default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-64bd6ab-guard | gmrtd | 64bd6ab-guard | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-8fea245-default | gmrtd | 8fea245-default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-8fea245-guard | gmrtd | 8fea245-guard | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-b861835-allow-fallback | gmrtd | b861835-allow-fallback | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-b861835-default | gmrtd | b861835-default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-gmrtd-b861835-guard | gmrtd | b861835-guard | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-jmrtd-catch-continue | jmrtd | catch-continue | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-jmrtd-propagate | jmrtd | propagate | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-success-passauf-default | passauf | default | 1 | 0 | 0 | 0 | 1 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-dmrtd-default | dmrtd | default | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-emrtd-dotnet-default | emrtd-dotnet | default | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-64bd6ab-allow-fallback | gmrtd | 64bd6ab-allow-fallback | 1 | 0 | 1 | 0 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-64bd6ab-default | gmrtd | 64bd6ab-default | 1 | 0 | 1 | 0 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-64bd6ab-guard | gmrtd | 64bd6ab-guard | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-8fea245-default | gmrtd | 8fea245-default | 1 | 0 | 1 | 0 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-8fea245-guard | gmrtd | 8fea245-guard | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-b861835-allow-fallback | gmrtd | b861835-allow-fallback | 1 | 0 | 1 | 0 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-b861835-default | gmrtd | b861835-default | 1 | 0 | 1 | 0 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-gmrtd-b861835-guard | gmrtd | b861835-guard | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-jmrtd-catch-continue | jmrtd | catch-continue | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-jmrtd-propagate | jmrtd | propagate | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |
| CELL-VSC-bac-only-wrong-mrz-passauf-default | passauf | default | 1 | 0 | 0 | 1 | 0 | 0 | 1 | n/a |

Canonical manifest: `artifact-manifest.json` · commit `be99fefd61a5fdf2e7b86a70337a900924d97b76`

In-process simulators are deterministic (no RNG, no concurrency). Each profile is therefore run at N=1; multi-profile cells (e.g. the 50-profile AC-01 sweep) establish consistency across profiles, not repeated identical trials. The ≥95% finding threshold applies only to multi-profile cells (n ≥ 2); single-profile cells are reported with the threshold marked not applicable.
[22:42:57] start: be99fef dirty=0
[22:43:00] gofmt: [] vet: ok
[22:43:00] pace: start
[22:50:03] pace: rc=0 SUITE OK — 416 runs under /home/test/cbo/u7-runs/pace/ VERIFY OK — /home/test/cbo/u7-runs/pace/artifact-manifest.json SUITE OK (/home/test/cbo/u7-runs/pace) 
[22:50:03] controls: start
[22:50:46] controls: rc=0 SUITE OK — 26 runs under /home/test/cbo/u7-runs/controls/ VERIFY OK — /home/test/cbo/u7-runs/controls/artifact-manifest.json SUITE OK (/home/test/cbo/u7-runs/controls) 
[22:50:46] independent: start
[22:54:27] independent: rc=0 SUITE OK — 325 runs under /home/test/cbo/u7-runs/independent/ VERIFY OK — /home/test/cbo/u7-runs/independent/artifact-manifest.json SUITE OK (/home/test/cbo/u7-runs/independent) 
[22:54:27] u7-bac: start
[22:54:58] u7-bac: rc=0 SUITE OK — 26 runs under /home/test/cbo/u7-runs/u7-bac/ VERIFY OK — /home/test/cbo/u7-runs/u7-bac/artifact-manifest.json SUITE OK (/home/test/cbo/u7-runs/u7-bac) 
[22:54:58] post: dirty=0
[22:54:58] U7 DONE
