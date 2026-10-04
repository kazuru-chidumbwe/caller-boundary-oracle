# Chip profiles

Each profile describes one chip behaviour: which mechanism is targeted, which step fails and how, and what the chip serves. Profiles are generated, not edited by hand.

| Directory | Contents |
| --- | --- |
| `pace/` | Harness chip: PACE failing at MSE:Set AT or General Authenticate, 13 status words and 3 channel faults |
| `ca/` | Harness chip: Chip Authentication rejected at MSE:Set AT |
| `aa/` | Harness chip: Active Authentication rejected at INTERNAL AUTHENTICATE |
| `controls/` | No PACE on offer (BAC only); PACE with proprietary domain parameters |
| `independent/` | Independent chip: PACE positive controls, PACE failing at each step, AA rejected under secure messaging |

Profiles that reproduce an ICAO inspection-system conformity case carry its ID in `icao_p4`.

`generate_profiles.py` writes the profiles; `generate_chip_fixtures.py` writes the EF.SOD, DG1 and other fixtures the chips serve (`simulator/fixtures/`). After changing either, regenerate the suites: `python3 suites/generate_suites.py`.
