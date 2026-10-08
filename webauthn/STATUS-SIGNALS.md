# WebAuthn arm: what each library tells its caller, and which fields count as a status signal

The observations are derived in `webauthn/run.py` (`observe`, `STATUS_FIELDS`); the oracle is `classifier/observability.py`, unchanged since the freeze at `f9f253d`.

**Rule.** A field of the result a library returns counts as a status signal for a fault only if its value alone states that the property the violated step enforces did not hold. A raw value that the caller would have to compare with something else does not count: a new signature count that must be compared with the stored count, or a BS flag that must be compared with the BE flag. `returned_error` is an exception (Python, JavaScript, Java, C#) or a non-nil error (Go) from the verification call.

| Library (arm) | Version | Call | Status fields and the faults they report on |
| --- | --- | --- | --- |
| py_webauthn | 3.0.1 | `verify_registration_response`, `verify_authentication_response` | `user_verified` (R-UV, A-UV) |
| simplewebauthn | 14.0.3 | `verifyRegistrationResponse`, `verifyAuthenticationResponse` | `verified` (every fault); `userVerified` (R-UV, A-UV) |
| go-webauthn | v0.18.2 | `CreateCredential`, `ValidateLogin` | `Flags.UserVerified` (R-UV, A-UV); `Authenticator.CloneWarning` (A-CNT) |
| java-webauthn-server | 2.10.0 | `finishRegistration`, `finishAssertion` (library defaults) | `isSuccess` (every A- fault); `isSignatureCounterValid` (A-CNT); `isUserVerified` (R-UV, A-UV) |
| webauthn4j (non-strict) | 0.31.11.RELEASE | `createNonStrictWebAuthnManager()`, `verify` | UV flag of the returned authenticator data (R-UV, A-UV) |
| webauthn4j (strict) | 0.31.11.RELEASE | packed and none verifiers, self attestation allowed, `verify` | as non-strict |
| fido2-net-lib | 4.2.0 (`9218d55`) | `MakeNewCredentialAsync`, `MakeAssertionAsync` (default configuration) | none: the result carries `IsBackupEligible`, `IsBackedUp` and `SignCount` as raw values only |

**Arms.** One caller choice is measured: webauthn4j offers two ways to build its manager, and the non-strict factory replaces the attestation statement verifiers with ones that do not verify. Every other library is called with its defaults and with user verification required, which is the relying-party policy that makes 7.1 step 16 and 7.2 step 17 mandatory.

**Pre-registration.** Expectations for an evaluation run are derived from each library's source at the pinned version, written to a file with the source reason for every entry, and committed before that run; the run is verified against the file with `python3 webauthn/run.py --expectations FILE`. The rule above is frozen with this file.
