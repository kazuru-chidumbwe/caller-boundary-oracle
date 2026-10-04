# Suite manifests

Each manifest lists runs (library, arm, profile) and the outcome the oracle is expected to report, written before the runs by `generate_suites.py`. The reasons for each expectation are comments in that script.

| Manifest | Contents |
| --- | --- |
| `pace.json` | PACE failures on the harness chip, every arm |
| `ca-aa.json` | Chip and Active Authentication rejections |
| `controls.json` | No-injection and interoperability controls |
| `independent.json` | Independent chip: PACE positive controls, PACE failures at each step, AA under secure messaging |
| `independent-repeat.json` | PACE positive control, 100 runs per library |
| `ios.json` | NFCPassportReader in the iOS Simulator |
| `smoke.json` | One PACE profile across every Linux arm |

Regenerate after changing profiles: `python3 profiles/generate_profiles.py && python3 suites/generate_suites.py`.
