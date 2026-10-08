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
