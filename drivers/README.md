# Library drivers

Each driver reads one chip profile, connects the library to a chip, calls the library the way an application would, applies the oracle, and writes one run artifact. The gmrtd driver is `cmd/gmrtd-read`.

| Directory | Library | Language | Chip connection |
| --- | --- | --- | --- |
| `jmrtd/` | JMRTD 0.8.9 | Java | `cmd/chip-serve` or the independent chip, over the vpcd socket |
| `dotnet/` | emrtd-dotnet | C# | `cmd/chip-serve` or the independent chip, over the vpcd socket |
| `dart/` | dmrtd | Dart | `cmd/chip-serve` or the independent chip, over the vpcd socket |
| `rust/` | passauf 0.2.0 (48b7cc7) | Rust | `cmd/chip-serve` or the independent chip, over the vpcd socket, through passauf's `CallbackSmartcard` |
| `ios/` | NFCPassportReader | Swift | XCTest in the iOS Simulator, through `tools/chip_broker.py` |

Every driver implements the same oracle and checks it against `testdata/observability-vectors.json` (`-check-vectors`).

**passauf driver (`rust/`): two driver rules.** (1) passauf panics when a response is missing or too short; its own app integration (`src/ffi/mod.rs`) wraps `read_document` in `catch_unwind` and hands the panic to the app as an error, and the driver does the same, so a panic counts as an error returned to the caller. (2) A `read_document` call that has not returned after 120 s is recorded as a hang (`"hang": true`): no error and no status reached the caller, so the frozen oracle classifies the observation as usual; hangs are also reported separately. The trace keeps the first 500 exchanges and the library log the first 2,000 lines, with counts of what was dropped.

