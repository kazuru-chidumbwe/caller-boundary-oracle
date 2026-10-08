# WebAuthn fault model: one fault per run, mapped to the relying-party steps

Source: W3C Web Authentication Level 3, W3C Recommendation of 25 August 2026 (https://www.w3.org/TR/webauthn-3/), section 7.1 "Registering a New Credential" and section 7.2 "Verifying an Authentication Assertion". Step numbers are the top-level steps of those sections, read from the published HTML on 8 October 2026.

The fault peer is a deterministic software authenticator (`webauthn/authenticator.py`). It builds a registration response or an assertion response that is correct except for one injected fault, and writes a delivery report naming the fault and the SHA-256 of the response it produced. A driver passes that response to the library unchanged; the run's `fired` observation is true when the hash of what the driver passed equals the reported hash and the report names an injected fault.

| ID | Ceremony | Fault | Step | What the step requires |
| --- | --- | --- | --- | --- |
| R-TYPE | registration | `clientDataJSON.type` is `webauthn.get` | 7.1 step 7 | Verify that C.type is `webauthn.create` |
| R-CHAL | registration | challenge differs from the one the relying party issued | 7.1 step 8 | Verify that C.challenge equals the base64url encoding of the issued challenge |
| R-ORIG | registration | origin is not the relying party's origin | 7.1 step 9 | Verify that C.origin is an origin expected by the relying party |
| R-RPID | registration | `rpIdHash` is the hash of another RP ID | 7.1 step 14 | Verify that the rpIdHash in authData is the SHA-256 hash of the expected RP ID |
| R-UP | registration | UP flag clear | 7.1 step 15 | Unless mediation is conditional, verify that the UP bit is set |
| R-UV | registration | UV flag clear while the relying party requires user verification | 7.1 step 16 | If the relying party requires user verification, verify that the UV bit is set |
| R-BS | registration | BS flag set while BE is clear | 7.1 step 17 | If the BE bit is not set, verify that the BS bit is not set |
| R-ASIG | registration | packed self-attestation with an invalid attestation signature | 7.1 step 22 | Verify that attStmt is a correct attestation statement, conveying a valid attestation signature |
| A-TYPE | authentication | `clientDataJSON.type` is `webauthn.create` | 7.2 step 10 | Verify that C.type is `webauthn.get` |
| A-CHAL | authentication | challenge differs | 7.2 step 11 | Verify that C.challenge equals the base64url encoding of the issued challenge |
| A-ORIG | authentication | origin differs | 7.2 step 12 | Verify that C.origin is an origin expected by the relying party |
| A-RPID | authentication | `rpIdHash` is the hash of another RP ID | 7.2 step 15 | Verify that the rpIdHash in authData is the SHA-256 hash of the expected RP ID |
| A-UP | authentication | UP flag clear | 7.2 step 16 | Verify that the UP bit is set |
| A-UV | authentication | UV flag clear while user verification is required | 7.2 step 17 | If user verification is required, verify that the UV bit is set |
| A-BS | authentication | BS flag set while BE is clear | 7.2 step 18 | If the BE bit is not set, verify that the BS bit is not set |
| A-SIG | authentication | assertion signature invalid | 7.2 step 21 | Verify that sig is a valid signature over authData and the client data hash |
| A-CNT | authentication | `signCount` lower than the stored count (both nonzero) | 7.2 step 22 | A count that does not increase "is a signal, but not proof, that the authenticator may be cloned"; whether to fail the ceremony is relying-party policy |

Positive controls: one correct registration and one correct authentication per library; nothing injected, outcome not applicable, and the ceremony must succeed.

Steps 7 to 21 of 7.1 and 10 to 21 of 7.2 are mandatory checks: a failure that the library does not turn into an error is a failure the caller can only learn about from a status field, or not at all. A-CNT is the one case the specification leaves to policy; a library that reports it in a field without failing behaves as the specification allows, and the oracle still records what the caller is told.

Attestation trust (7.1 step 24) is not injected: whether an attestation is trusted depends on the relying party's trust anchors, which each library configures differently, so a fault there would measure configuration rather than failure reporting. This is stated as a limitation.
