# Caller-boundary oracle

A test harness and oracle for one question: when a security step inside a library fails, does the application that called the library find out?

The harness injects a single failure into one negotiation or authentication step, drives the library through the API an application would use, and records what reaches the caller. The oracle turns those observations into one of five outcomes. The current case study is electronic passport (eMRTD) reader libraries: PACE, Chip Authentication (CA) and Active Authentication (AA), across five libraries in five languages.

Everything runs against emulated chips. No passport or NFC hardware is needed.

## The oracle

Each run records five observations. `fired` comes from the chip (the injected failure was actually delivered); the other four come from the library and the calling code.

| Observation | Meaning |
| --- | --- |
| `fired` | The chip delivered the injected failure |
| `failed` | The library recorded the targeted step as failed |
| `succeeded` | The library recorded the targeted step as successful |
| `returned_error` | The call returned an error or threw |
| `status_signal` | The failure is visible in a returned status field |

The outcome is decided in this order:

| Outcome | Rule | Score |
| --- | --- | --- |
| `invalid` | `failed` and `succeeded` both true | none |
| `not_applicable` | the failure did not fire | none |
| `surfaced` | an error reached the caller | 2 |
| `status_only` | the call succeeded; the failure is only in a status field | 1 |
| `silent` | the call succeeded and nothing the caller can see records the failure | 0 |

The same predicate is implemented in Go, Python, Java, C# and Dart (`classifier/`, `drivers/`), and every implementation is checked against the shared vectors in `testdata/observability-vectors.json`.

## Subjects

| Library | Language | Pinned at | Driven through |
| --- | --- | --- | --- |
| [gmrtd](https://github.com/gmrtd/gmrtd) | Go | v0.45.0 (8fea245), v1.1.3 (64bd6ab), v1.3.2 (b861835) | `reader.ReadDocument`: default, opt-in BAC fallback, and with the caller guard in `guard/` |
| [JMRTD](https://jmrtd.org) | Java | 0.8.9 | `PassportService`, with two integrator patterns: propagate, and catch-and-continue |
| [emrtd-dotnet](https://github.com/chamnan/emrtd-dotnet) | C# | 0433b3a | `DocumentReader.Read` |
| [dmrtd](https://github.com/ZeroPass/dmrtd) | Dart | 3b6c091 | `Passport.startSessionPACE` / `startSession`, `activeAuthenticate` |
| [NFCPassportReader](https://github.com/AndyQ/NFCPassportReader) | Swift (iOS) | 6e37f1a | `PassportReader.startReading`, in the iOS Simulator |

All three gmrtd versions build from one source tree (`internal/gmrtdcompat`, build tags and `gomod/`).

## Chips

Two independent chips answer the libraries.

1. **Harness chip** (`simulator/`, served over a socket by `cmd/chip-serve`). Deterministic; fails exactly the configured step with the configured status word or channel fault; reports whether the failure was delivered.
2. **Independent chip** (`tools/vsmartcard/emrtd_card.py`). The [vsmartcard](https://github.com/frankmorgner/vsmartcard) nPA card with [OpenPACE](https://github.com/frankmorgner/openpace) for PACE, plus an eMRTD application, BAC, and secure messaging that follows ICAO Doc 9303 Part 11. It shares no code with the harness chip or the libraries. It provides the PACE positive controls and fails PACE at MSE:Set AT and at each General Authenticate step.

Both chips write the same delivered-fault report, so every driver decides `fired` the same way.

## Fault space

- **PACE:** failure at MSE:Set AT and at General Authenticate steps 1 to 4 (steps 2 to 4 need real PACE, so they run on the independent chip).
- **CA:** rejected at MSE:Set AT. **AA:** rejected at INTERNAL AUTHENTICATE.
- **Status words:** 6300, 6700, 6800, 6900, 6982, 6A00, 6A80, 6A88, 6B00, 6C00, 6E00, 6F00, 6FFF. **Channel faults:** no response, timeout, transport abort.
- The status-word sets include every PACE and CA status-word case of the ICAO inspection-system conformity tests (ICAO TR RF and Protocol Testing Part 4, cases C_08, C_10, C_12, C_18, C_24 and G_15). Profiles that reproduce one carry its case ID in `icao_p4`. Those tests have no status-word case for Active Authentication; the AA cells here do.
- **Controls:** a chip without PACE (BAC only), PACE with proprietary domain parameters, and PACE positive controls on the independent chip.

## Expected outcomes

Every suite entry states its expected outcome before it runs (`suites/generate_suites.py` writes them; the reasons are in the comments there). `classifier/verify_manifest.py` fails a run if any outcome or pinned observation differs. Nondeterministic cases (PACE against the independent chip, which uses fresh ephemeral keys) are measured in `suites/independent-repeat.json`, 100 runs per library.

| Suite | Runs | Contents |
| --- | --- | --- |
| `pace` | 384 | PACE failures on the harness chip, every arm |
| `ca-aa` | 221 | CA and AA rejections |
| `controls` | 24 | No-injection and interoperability controls |
| `independent` | 285 | Independent chip: PACE positive controls, PACE failures at every step, AA under secure messaging |
| `independent-repeat` | 600 | PACE positive control, 100 runs per library |
| `ios` | 87 | NFCPassportReader, every profile (GitHub Actions, macOS) |
| `smoke` | 12 | One PACE profile across every Linux arm |

## Quick start (Linux)

Requirements: Go 1.26, Java 17 and Maven, Python 3.11 or later, and the build tools for OpenPACE (Debian: `autoconf automake libtool pkg-config libssl-dev swig python3-dev gengetopt help2man`). The .NET SDK and the Dart SDK are installed into `../_vendor` by their bootstrap scripts.

```bash
git clone https://github.com/kazuru-chidumbwe/caller-boundary-oracle.git
cd caller-boundary-oracle
bash scripts/bootstrap-vendor.sh   # gmrtd at the three pins, JMRTD
make vsmartcard                    # independent chip (OpenPACE + vsmartcard)
make dotnet                        # .NET SDK + emrtd-dotnet
make dart                          # Dart SDK + dmrtd
make test                          # oracle vectors in all five languages, Go tests at all pins
make smoke                         # one profile across every arm, verified
make evaluate                      # every Linux suite, each verified against its expectations
```

One suite: `make suite MANIFEST=suites/pace.json`. Run artifacts go to `logs/`; verified summaries to `artifacts/`.

## iOS

NFCPassportReader runs in the iOS Simulator under XCTest with a socket-backed tag (`drivers/ios/`). The Simulator has no NFC, so `tools/chip_broker.py` on the macOS host connects each run to either chip. `.github/workflows/ios.yml` builds everything, runs `suites/ios.json`, and verifies it with the same manifest check as Linux.

## Patches to third-party code

Kept small and listed so their effect can be checked.

| Patch | What it changes | Why it cannot change the measured behaviour |
| --- | --- | --- |
| `drivers/ios/nfcpassportreader-test-visibility.patch` | Eight `private var` properties of `PassportReader` become internal | Access level only, so the test can set read options and call `startReading` without an NFC session |
| `drivers/dart/` stubs | Stand-ins for `flutter_nfc_kit`, `expandable` and `diffie_hellman` | dmrtd declares them but its reader code does not use them: `flutter_nfc_kit` is imported only by dmrtd's NFC provider, which the driver replaces with its own transport; `expandable` only by dmrtd's example app; `diffie_hellman` nowhere. `scripts/bootstrap-dart.sh` checks these import facts against the pinned dmrtd. No dmrtd code is changed |
| `tools/vsmartcard/vsmartcard-python3.patch` | Four str/bytes fixes in vsmartcard | Affects the independent chip only, not a library under test |

## Layout

```
classifier/   oracle (Python), suite runner, aggregation, manifest verification
cmd/          gmrtd driver (gmrtd-read) and the socket chip server (chip-serve)
drivers/      JMRTD (Java), emrtd-dotnet (C#), dmrtd (Dart), NFCPassportReader (Swift)
guard/        opt-in caller guard for gmrtd (require PACE, CA or AA)
internal/     gmrtd version shims, run logic, profiles, provenance, output
mining/       item lists for the code studies (failure-handling sites)
profiles/     chip profiles and their generators
simulator/    harness chip and the vsmartcard peer
suites/       suite manifests with expected outcomes, and their generator
testdata/     shared oracle vectors, DG14 and DG15 samples
tools/        independent chip card script, iOS broker, plan and collector
scripts/      bootstrap, run, evaluate and reproduction scripts
```

## Provenance

Each run artifact records the harness commit and whether the tree was clean, the library commit or version, toolchain versions, the profile path and its SHA-256, the suite, and the run index. Aggregation writes `artifact-manifest.json` per suite with per-run hashes; `make verify-manifest` re-checks a log directory against its manifest.

## Security

See [SECURITY.md](SECURITY.md). Defects found in third-party libraries are reported to their maintainers before they are described here.

## License and citation

MIT, see [LICENSE](LICENSE). The libraries under test, vsmartcard and OpenPACE keep their own licenses. To cite this software, use [CITATION.cff](CITATION.cff).
