# Changelog

## 1.0.0

First release.

- Caller-boundary oracle with five outcomes (surfaced, status-only, silent, not applicable, invalid), implemented in Go, Python, Java, C# and Dart and checked against shared vectors.
- Drivers for gmrtd (v0.45.0, v1.1.3, v1.3.2), JMRTD 0.8.9, emrtd-dotnet, dmrtd and NFCPassportReader (iOS Simulator).
- Harness chip with failure injection at PACE (MSE:Set AT, General Authenticate), Chip Authentication and Active Authentication; 13 status words and 3 channel faults, covering the ICAO inspection-system conformity status-word cases.
- Independent chip on vsmartcard and OpenPACE with BAC and Doc 9303 secure messaging, for PACE positive controls and PACE failures at every General Authenticate step.
- Suite manifests with pre-registered expected outcomes, aggregation with per-run hashes, and manifest verification; Linux and iOS CI.
- Item list for the code study of failure-handling sites (mining/).
