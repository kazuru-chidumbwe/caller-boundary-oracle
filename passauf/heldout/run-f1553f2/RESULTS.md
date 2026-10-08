# passauf held-out run of record (harness f1553f2, 8 October 2026)

passauf v0.2.0 (`48b7cc7d7398bbdfdcfef2c900a01972275c6c8a`), the sixth eMRTD library, studied as a held-out subject: its expected outcomes were written from its source and committed in `af4a92d` before passauf was run at all. Driver `drivers/rust` (passauf's `read_document` through its `CallbackSmartcard`, the transport passauf documents for bringing your own reader), Rust 1.92.0, Testbed A. Manifest `suites/heldout-passauf.json`: every passauf entry of `pace.json`, `independent.json`, `independent-repeat.json` and `controls.json`, 49 entries, 148 runs; aggregated with `suites/heldout-passauf-aggregate.json`, which merges the two `VSC-pace-success` entries (1 + 100 runs) into one.

Files: `results.jsonl` (one line per run, without the APDU trace), `COMPARE.json` (each run against its expectation, `analysis/compare_expectations.py`), `artifact-manifest.json`, `summary.json`, `summary.md`, `environment.json`. Full artifacts with traces stay on Testbed A (`/home/test/cbo/passauf-runs/heldout-f1553f2`, archive `/tmp/passauf-full-f1553f2.tgz`).

## Result

| | Count |
| --- | ---: |
| Runs | 148 |
| Cells (test case) | 48 |
| Cells where every run matched its expectation | 41 |
| Runs matched / not matched | 141 / 7 |
| Outcomes | not_applicable 104, status_only 37, surfaced 6, silent 1 |

The 41 matching cells are 25 of the 26 status-word faults on the harness chip (13 status words at MSE:Set AT and at General Authenticate; all but 6C00), the 12 fault cells on the independent chip, both controls, and the two independent success cells, with 101 of 101 `VSC-pace-success` runs establishing PACE (`PACE-ECDH-Generic Mapping with AES-CBC-CMAC-128`). In each of these 25 cells `read_document` returns a document, `DocumentRead.authentication` names BAC, and the PACE error is only in the library log.

## The seven cells that did not match

| Cell | Expected | Observed | What passauf does |
| --- | --- | --- | --- |
| PACE-mse-set-at-no-response, -timeout, -transport-abort | status_only | surfaced | The chip returns an empty response. `CallbackSmartcard::exchange_apdu` returns `None` for a response shorter than two bytes, and `ApduCommand::exchange` (src/iso7816.rs line 301) calls `expect` on it: the library panics ("The card stopped responding mid-exchange, most likely because it moved out of the reader's field."). |
| PACE-general-authenticate-no-response, -timeout, -transport-abort | status_only | surfaced | Same panic, in `exchange_step_objects` during PACE. |
| PACE-mse-set-at-6c00 | status_only | silent (hang) | Status word 6CXX tells the reader to resend with Le = XX, and passauf does so for any 6CXX (`iso7816.rs` line 326, no bound). The resent MSE:Set AT is accepted (9000); from then on the harness chip answers every PACE command with 6C00, and passauf resends General Authenticate with Le = 00 without end (488 of the 500 kept exchanges, 2,293 more dropped from the trace). The call had not returned after 120 s; no error and no status reached the caller. |

The expectations were derived from passauf's PACE fallback path (`session.rs`, any PACE error falls back to BAC). They missed that a missing response never reaches that path, because the transport layer panics first, and that a 6CXX answer is retried without a bound. passauf's own Android integration (`src/ffi/mod.rs`) catches the panic with `catch_unwind` and passes it to the app as an error; the driver does the same, so the panic counts as an error returned to the caller. An application that calls `read_document` directly, without `catch_unwind`, terminates.

## Runs before this one

Two earlier runs of the same manifest stopped and were archived as invalid on Testbed A: `07e0aa2` (the driver did not catch the panic and exited at PACE-general-authenticate-no-response) and `2e0a1a0` (the driver had no call limit and waited forever at PACE-mse-set-at-6c00). Both faults were in the driver; the expectations were not changed. Debug runs of the driver used copies of profiles under `/tmp` (the no-fault vsmartcard PACE success, and copies of the no-response and 6C00 profiles after the first two runs had shown their behaviour).
