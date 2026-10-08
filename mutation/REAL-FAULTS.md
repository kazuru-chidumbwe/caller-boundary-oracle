# Real failure-reporting changes behind the mutation operators

Each kind of change that the mutation study scores has happened in the history of the libraries studied. The rows below come from the libraries' own commits (read 8 October 2026 from the pinned clones); the "before" and "after" columns state what a caller is told after the failure, in the terms of the oracle. The operators model the "before" side of each fix, or the "after" side where the change itself reduced what the caller is told.

| Kind of change (oracle terms) | Operator | Library and commit | What the code did | Before | After |
| --- | --- | --- | --- | --- | --- |
| surfaced to status-only | O2 at a fail-closed check, O3 | NFCPassportReader `35a2e4f` (2021-03-15), "No longer fails if PACE fails" | A PACE error used to end the session with an error to the caller; now `PACEStatus = .failed` is set and reading continues with BAC | surfaced | status-only |
| status-only to surfaced (and back as an opt-in) | O2, O5 at the same check | gmrtd 0.45.0 to 1.1.3 (`64bd6ab`, includes pull request #446) | A recorded PACE error used to be followed by BAC; now `ReadDocument` returns the error unless the caller opts in to BAC fallback | status-only | surfaced (default); status-only (opt-in) |
| silent to status-only | O4 | NFCPassportReader `4541285` (2022-06-12), "Now sets correct CA Status when CA fails" | `chipAuthenticationStatus` was set to `.success` even when Chip Authentication failed; now it records the result | silent (failure recorded as success) | status-only |
| silent to surfaced | O1, O2 | NFCPassportReader `9e02fab` (2023-03-22), "report errors back instead of returning nil" | After the last failed attempt the read returned `nil`; now it throws the last error | silent | surfaced |
| error status treated as success | O2, O5 | NFCPassportReader, open pull request #272 (third party) | A response counts as an error only if both status bytes differ from 9000, so every status word with SW2 = 00 is treated as success | (current) status-only for 9 status words | surfaced (proposed) |
| error response returned as data | O1, O3 | JMRTD 0.8.9, `AAAPDUSender.sendInternalAuthenticate` (defect D2 in the paper) | Any response object is returned as the signature regardless of its status word | silent (current) | (report filed separately) |
| which status words raise | O5 | dmrtd `93e2ac3` (2020-11-15) | `_readBinary` throws when the status is an error (`isError()`) instead of when it is not success; warning status words no longer throw | surfaced for warnings | not raised for warnings |

Reading the table: the two classes that the baseline oracles cannot see both occur in practice. A change between surfaced and status-only (NFCPassportReader `35a2e4f`; gmrtd 0.45.0 to 1.1.3) is invisible to a verdict that only asks whether the failure was indicated somewhere. A change between silent and status-only (NFCPassportReader `4541285`) is invisible to a check for returned errors and to a comparison of accepted and rejected reads, because no error is returned on either side.

Disclosure: the gmrtd change from 0.45.0 to 1.1.3 was proposed by the author of this study (pull request #446). It is listed because it is a real change in a released library, not as independent evidence.
