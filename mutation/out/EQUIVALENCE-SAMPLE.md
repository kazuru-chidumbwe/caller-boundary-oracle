# Hand check of reached mutants that no oracle killed (8 October 2026)

Population: 140 mutants whose site ran on at least one arm (reach.json) and for which no oracle saw any change. Sample: 30, drawn by `mutation/equivalence_sample.py` (seed 20261008). Each was classified by reading the mutated code in context.

| Class | Count | Meaning |
| --- | ---: | --- |
| Not exercised | 20 | The check only matters for a fault outside the fault model: a malformed or malicious value from the chip (invalid EC point, broken dynamic-authentication object, invalid key data) or a local error that valid inputs cannot cause |
| Masked | 9 | The mutant skips a failure check at or near the injection point, but a later step fails and reports the same failure, so what the caller is told does not change |
| Equivalent | 1 | The changed branch cannot run: the error cannot occur with the constant arguments used |

No sampled mutant is a failure-reporting change that the oracles missed.

| Mutant | Site | Class | Reason |
| --- | --- | --- | --- |
| M1-0083-b861835-O2 | gmrtd pace/pace.go:340 | Not exercised | Error only for an invalid EC point from the chip |
| M1-0025-b861835-O2 | gmrtd chipauth/chip_auth.go:58 | Not exercised | Error only for a DG14 without a usable CA public key |
| M1-0130-x-O5 | JMRTD AAAPDUSender.java:106 | Masked | On a refused INTERNAL AUTHENTICATE both branches return the response data (defect D2); a successful AA never occurs in the suite |
| M1-0079-8fea245-O2 | gmrtd pace/pace.go:293 | Not exercised | Error only for an invalid password type |
| M1-0071-64bd6ab-O2 | gmrtd pace/auth_token.go:77 | Equivalent | `cmac.Sum` with tag length 8 cannot fail |
| M1-0082-b861835-O2 | gmrtd pace/pace.go:336 | Not exercised | Error only for a malformed dynamic-authentication object |
| M1-0037-8fea245-O2 | gmrtd chipauth/chip_auth.go:415 | Not exercised | Error only for invalid CA key data |
| M1-0077-64bd6ab-O2 | gmrtd pace/pace.go:221 | Not exercised | Error only for an encrypted nonce that is not a whole number of blocks |
| M1-0085-8fea245-O2 | gmrtd pace/pace.go:398 | Not exercised | Error only for a malformed dynamic-authentication object |
| M1-0077-8fea245-O2 | gmrtd pace/pace.go:222 | Not exercised | As M1-0077-64bd6ab |
| M1-0110-b861835-O2 | gmrtd pace/pace.go:748 | Not exercised | Error only for an invalid password |
| M1-0049-64bd6ab-O5 | gmrtd iso7816/nfc_session.go:108 | Masked | On a refused AA the inverted branch returns an error as the status check below it would |
| M1-0317-x-O1 | emrtd-dotnet Pace.cs:123 | Not exercised | Throw only when the chip's mapping point yields the point at infinity (malicious chip) |
| M1-0002-8fea245-O5 | gmrtd activeauth/active_auth.go:228 | Masked | After a refused AA, signature validation fails and records the same failure |
| M1-0076-64bd6ab-O2 | gmrtd pace/pace.go:214 | Not exercised | Error only for an unsupported cipher |
| M1-0073-8fea245-O2 | gmrtd pace/auth_token.go:104 | Not exercised | Error only from token computation with invalid keys |
| M1-0039-b861835-O2 | gmrtd chipauth/chip_auth.go:438 | Masked | Skipping the MSE:Set AT error leads to a failing General Authenticate; CA is recorded as failed |
| M1-0049-64bd6ab-O2 | gmrtd iso7816/nfc_session.go:108 | Not exercised | Transport errors during AA are not injected (AA cells inject status words) |
| M1-0070-64bd6ab-O2 | gmrtd pace/auth_token.go:72 | Not exercised | Error only for an unsupported cipher |
| M1-0078-64bd6ab-O2 | gmrtd pace/pace.go:253 | Not exercised | Error only for undecodable TLV from the chip |
| M1-0024-8fea245-O2 | gmrtd chipauth/chip_auth.go:53 | Not exercised | Error only for a DG14 without CA information |
| M1-0039-64bd6ab-O2 | gmrtd chipauth/chip_auth.go:438 | Masked | As M1-0039-b861835 |
| M1-0488-8fea245-O2 | gmrtd reader/reader.go:292 | Masked | A missing EF.CardAccess then fails to parse, which the reader treats the same way |
| M1-0082-8fea245-O2 | gmrtd pace/pace.go:337 | Not exercised | As M1-0082-b861835 |
| M1-0111-64bd6ab-O2 | gmrtd pace/pace.go:753 | Masked | Skipping the MSE:Set AT error leads to a failing nonce request; PACE is recorded as failed |
| M1-0112-b861835-O2 | gmrtd pace/pace.go:760 | Masked | Skipping the nonce error leads to a failing mapping step; PACE is recorded as failed |
| M1-0070-8fea245-O2 | gmrtd pace/auth_token.go:72 | Not exercised | As M1-0070-64bd6ab |
| M1-0098-64bd6ab-O2 | gmrtd pace/pace.go:608 | Not exercised | Error only for an invalid password |
| M1-0367-x-O1 | dmrtd ecdh_pace.dart:386 | Not exercised | Throw only for an unknown domain parameter ID |
| M1-0080-64bd6ab-O2 | gmrtd pace/pace.go:305 | Masked | Skipping the MSE:Set AT error leads to a failing next step; PACE is recorded as failed |
