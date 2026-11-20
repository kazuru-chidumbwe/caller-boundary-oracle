# Changelog

## 1.0.0 (unreleased)

First release.

- Caller-boundary oracle with five outcomes (surfaced, status-only, silent, not applicable, invalid), implemented in Go, Python, Java, C# and Dart and checked against shared vectors.
- eMRTD drivers for gmrtd (v0.45.0, v1.1.3, v1.3.2), JMRTD 0.8.9, emrtd-dotnet, dmrtd, NFCPassportReader (iOS Simulator) and passauf (Rust, held out).
- Rechecks of later releases with expectations committed before each run: gmrtd v1.4.0, v1.9.1 and v1.10.0, JMRTD 0.8.10, passauf v0.2.1, NFCPassportReader 3.0.0 and 3.0.1.
- Harness chip with failure injection at PACE (MSE:Set AT, General Authenticate), Chip Authentication and Active Authentication; 13 status words and 3 channel faults, covering the ICAO inspection-system conformity status-word cases.
- Independent chip on vsmartcard and OpenPACE with BAC and Doc 9303 secure messaging, for PACE positive controls, PACE failures at every General Authenticate step, and Chip Authentication.
- WebAuthn relying-party arm: a software authenticator as fault peer and drivers for six libraries, with held-out releases.
- Mutation analysis of failure-reporting sites, with a reachability probe and four oracles for comparison.
- Suite manifests with pre-registered expected outcomes, aggregation with per-run hashes, and manifest verification; Linux and iOS CI.
- Item lists and protocol for the code study of failure-handling sites (`mining/`).
