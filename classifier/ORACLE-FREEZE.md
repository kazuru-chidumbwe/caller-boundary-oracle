# Oracle freeze before the second domain (8 October 2026)

The caller-boundary oracle (Algorithm 1 in the paper) is frozen at harness commit `f9f253d`, before any WebAuthn code is written. The WebAuthn arm must reuse one of these implementations byte for byte; the claim that the oracle transfers unchanged is checked by comparing these hashes at the end of that work. Any later change to an oracle file is a deviation: it is recorded below with its date and reason, and results are reported with both versions.

| Implementation | File | SHA-256 |
| --- | --- | --- |
| Python | `classifier/observability.py` | `e29e03eca5bfd6b935453a5bac7af68a6449564ede074e284c6156e4014a1bb9` |
| Go | `classifier/observability.go` | `5014689b982fd3e6d6c1089e65e5e17c871f392f102bc0cc7f5d7054560fe378` |
| Java | `drivers/jmrtd/src/main/java/org/callerboundary/jmrtd/Observability.java` | `9d8da7c2530cac8c985c6bdd12e2f1423a0a88a65a8ed063352f12e958f04b64` |
| C# | `drivers/dotnet/Oracle.cs` | `6b661f4525fc7c31774611c115e35c6d2a2c5bb7d82fa1c5a62348e6e4b21f44` |
| Dart | `drivers/dart/bin/dmrtd_read.dart`, lines 18 to 33 only (the `Observation` class, `classify` and `score`; the rest of the file is the driver) | `12ffb10a098d6e075d848e482542965c4522659d645f6f97d8f620bacba9e478` |
| Shared test vectors | `testdata/observability-vectors.json` | `830e3adf7bbb5bee59a8182b3a518a2ccd228fbe72264a9e05fa2cabcd820e90` |

Check: `sha256sum` on each file (for Dart: `sed -n 18,33p drivers/dart/bin/dmrtd_read.dart | sha256sum`).

## Deviations

None.

## Transfer check (WebAuthn arm, 8 October 2026)

The WebAuthn development run (`webauthn/dev/2026-10-08-11d3916/RUN.json`, harness `11d3916`, clean tree) classified every run with `classifier/observability.py`, SHA-256 `e29e03eca5bfd6b935453a5bac7af68a6449564ede074e284c6156e4014a1bb9`, the value frozen above. No oracle file was changed for the second domain; the domain-specific work is in the fault peer, the drivers and the status-field rule (`webauthn/STATUS-SIGNALS.md`).
