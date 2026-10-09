# Pre-registration ledger

Every set of expected outcomes, with the commit that fixed it before the run it governs, and every later change, numbered. Commits are in this repository unless stated. The paper claims pre-registration only for held-out subjects (Section 4.5); the development sets are listed here because their expectations verify the harness, and their changes are part of the record.

## A. Sets of expectations

| Set | Subjects | Fixed in | Run of record | Outcome |
| --- | --- | --- | --- | --- |
| A1 eMRTD suites (pace, ca-aa, controls, independent, independent-repeat, ios), development libraries | gmrtd (3 releases), JMRTD, emrtd-dotnet, dmrtd, NFCPassportReader | from the 3 Oct snapshot `50ef043` on; current form at `8f7e39c` | Linux suites at `8f7e39c`, CI and iOS at `1685d41` | all held |
| A2 JMRTD Chip Authentication cells | JMRTD 0.8.9, both integrator arms | `866f59b`, before any run | `8f7e39c` | 26 of 26 held |
| A3 RQ1 mutation design | five development libraries | `mutation/DESIGN.md`, frozen with changes 1 to 5 before any mutant | `mutation/out/RESULTS.md` | results under the frozen rules reported unchanged |
| A4 gmrtd version sweep | gmrtd 0.40.0 to 1.3.2 | driver and profiles unchanged from A1 | `analysis/out/VERSION-SWEEP.md` | descriptive; no expectations per release |
| A5 WebAuthn held-out | 13 arms (7 pinned, 6 held-out releases), 31 cases | `webauthn/heldout/expectations.json`, `26e1d88`, before the single run | `webauthn/heldout/run-0f5983b` | 263 of 263 held-out pairs held |
| A6 passauf held-out | passauf 0.2.0 (48b7cc7) | `suites/` entries, `af4a92d`, before any passauf run | `passauf/heldout/run-f1553f2` | 41 of 48 cells held; 7 not held (below) |
| A7 Code-study protocol and codebook | M1, M2 | `mining/PROTOCOL.md` and `mining/CODEBOOK.md`, frozen 8 Oct before any item was coded | coding not started | n/a |

## B. Changes after an expectation set was fixed

1. **A1, dmrtd multi-SecurityInfo control (1 entry).** Predicted "read refused"; observed a read over BAC with no error (CI evaluate failed on `8c99c76`, `ccbc171`, `63b4c0a`, 3 Oct). Expectation changed in `d48ed7e` (4 Oct). A failed prediction; the observation is defect D7.
2. **A1, JMRTD Active Authentication on the harness chip (10 entries per arm).** A Java-only harness simulator answered errors in plain, contrary to Doc 9303 Part 11; found when the two chips disagreed on exactly these cells. Simulator removed, expectation changed in `cfa76e1` (4 Oct). A harness defect, not a library prediction (paper 6.5).
3. **A1, JMRTD catch-and-continue, PACE MSE:Set AT 6A88 on the independent chip (1 run).** Expected silent, observed surfaced once (CI `63b4c0a`); caused by the independent chip's 7-byte send sequence counter, fixed in `d48ed7e`; not reproduced after, expectation unchanged.
4. **A3, changes 6 to 11 of `mutation/DESIGN.md`**, recorded after the first scoring: reachability probe, kills by run type, the arm as unit of analysis, second site-list correction (526 to 534), O4 for Go, negative control. Reported as exploratory, next to the frozen results.
5. **A5, development run reclassified.** The WebAuthn run `11d3916` had expectations written after the development runs; it was moved to `webauthn/dev/` and is not reported as pre-registered. The held-out set A5 replaced it.
6. **A6, two runs archived as invalid**, both for driver faults, with the expectations unchanged: `07e0aa2` (the driver did not catch a library panic) and `2e0a1a0` (the driver had no call limit and waited forever at PACE-mse-set-at-6c00).
7. **A6, seven cells not held**, reported as observed: the six channel-fault cells surfaced through a panic instead of being status-only (D9), and PACE-mse-set-at-6c00 did not return (D8).
8. **A7, change 1:** codebook v1.1 (coder B's review), before any item was coded.
9. **A7, change 2:** M1 site list extended to passauf (140 sites), before any item was coded.
