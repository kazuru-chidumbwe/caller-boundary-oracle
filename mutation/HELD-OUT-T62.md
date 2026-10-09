# Held-out application of the frozen mutation design to WebAuthn libraries (T62)

Written 9 October 2026, before any held-out mutant was generated, built or run. The four libraries below took no part in developing the mutation design; their drivers and fault peer were built for the WebAuthn arm (`webauthn/`), whose held-out run `0f5983b` is complete.

## What is frozen and taken unchanged

| Element | Source | Commit |
| --- | --- | --- |
| Operators O1 to O5 and their site kinds | `mutation/make_mutants.py` (operator code unchanged since e7dc4d7; later commits add command-line options only) | e7dc4d7 |
| Unit of analysis, run kinds (delivered, delivery, control), deduplication | `mutation/per_arm.py`, `mutation/DESIGN.md` changes 6 to 11 | 4ecfa64, 1098715 |
| Four oracles and the kill rule | `mutation/score.py` | 6dc7636 |
| Reachability probe and its negative control | `mutation/probe.py`, DESIGN change 6 and 11 | 20d0a38, 1098715 |
| Outcome classification | `classifier/observability.py`, SHA-256 e29e03eca5bf... (classifier/ORACLE-FREEZE.md) | unchanged |
| Site patterns per language | `mining/m1_sites.py` PATTERNS and FUNC for go, java, cs | as committed for M1 |

## What is new, because the domain is new (fixed now)

**Subjects and pinned releases** (the releases of the WebAuthn arm; sources at the tag):

| Library | Release | Source | Arms |
| --- | --- | --- | --- |
| go-webauthn | v0.18.2 | Go module cache copy | go-webauthn |
| java-webauthn-server | 2.10.0 | git tag 2.10.0 (0e2db1a), module `webauthn-server-core` | java-webauthn-server |
| webauthn4j | 0.31.11.RELEASE | git tag (fb63b0d), module `webauthn4j-core` | webauthn4j-strict, webauthn4j-nonstrict |
| Fido2 (fido2-net-lib) | 4.2.0 | git tag 4.2.0 (9218d55), project `Src/Fido2` | fido2-net-lib |

py_webauthn and simplewebauthn are not mutated: `make_mutants.py` has no operators for Python or TypeScript, and none are added.

**Sites.** Every line of the library's main (non-test) sources above that the unchanged M1 patterns mark as a decision site. Test, example and metadata-service sources are excluded by path (`_test.go`, `src/test/`, `Test`, `metadata/`, `Metadata/`). No site is added or removed by hand.

**Step.** The WebAuthn analogue of PACE, CA and AA is the ceremony. A site's step is REG if its file or function name refers to registration or attestation (`regist`, `attestation`, `MakeNewCredential`, `CreateCredential`, `FinishRegistration`), AUTH if it refers to authentication or assertion (`assert`, `login`, `authentic`, `MakeAssertion`, `FinishAssertion`), and BOTH otherwise.

**Runs per mutant.** The analogue of the reduced suite: every fault case of the mutant's ceremony that the pinned release ran in the held-out run (development and held-out cases), plus the three positive controls; a BOTH site runs both ceremonies. Every arm of the library runs (webauthn4j: both managers). The unmutated library first runs the same entries and must reproduce the outcomes of run `0f5983b` for the pinned release; if not, no mutant of that library runs.

**Build.** Go: the driver is built against the mutated copy through a `replace` directive. Java: the mutated source file is compiled against the release jar and its dependencies (Lombok as annotation processor where the file uses it) and its classes are placed before the release jar on the classpath, as for JMRTD. Fido2: the driver is built against the mutated project instead of the NuGet package. A mutant that does not compile is reported and scored for no oracle.

**Analysis.** `per_arm.py` and `score.py`, unchanged, on the run records. Reported in Section 5.1 next to the development results; nothing is pooled with them.

## Not decided by results

If the probe shows that a library's verification is mostly unreached by the cases, that is reported as it is; no case is added for T62.
