# What counts as a status signal, per library

The oracle's `status_signal` observation is true when the failure is visible to the caller in a field of what the library returns. Which field that is depends on the library. Each mapping below is in the driver code at the snapshot commit `50ef043` (3 October 2026), before any of the evaluation runs it scores, and is unchanged since.

| Library | Field the caller can read | Kind | Where |
| --- | --- | --- | --- |
| gmrtd | The session returned with the document records each step's error (`PaceErr`, `ChipAuthErr`, `ActiveAuthErr`; for access control also `BacErr` where BAC was used, ledger B.10) | Explicit: names the failed step | `internal/gmrtdrun/gmrtdrun.go` (`StatusSignal: session != nil && failed`) |
| NFCPassportReader | `PACEStatus` and `chipAuthenticationStatus` take the value `.failed`; for Active Authentication, `activeAuthenticationPassed` is false while `activeAuthenticationSupported` is true | Explicit for PACE and CA; a result flag for AA | `tools/ios_collect.py` (`step_state`) |
| emrtd-dotnet | The returned document names the access control used; when PACE was offered and the document names BAC, PACE did not complete. The PACE error itself goes only to a log callback | **Indirect**: the caller must infer the failure from the access control | `drivers/dotnet/Program.cs` (`StatusSignal: accessControl is not null && !succeeded`) |
| JMRTD | None: failures are thrown or not reported | n/a | `drivers/jmrtd/.../JmrtdRead.java` (always false) |
| dmrtd | None: failures are thrown | n/a | `drivers/dart/bin/dmrtd_read.dart` (always false) |

## Sensitivity

Under a strict reading, in which only a field that names the failed step counts, the emrtd-dotnet mapping is the only one that changes. Its PACE failures (32 on the harness chip and 12 on the independent chip, 44 runs) would then be silent rather than status-only. No other cell of the evaluation changes, and the mutation study has no failure-reporting change in emrtd-dotnet, so its results do not change either.
