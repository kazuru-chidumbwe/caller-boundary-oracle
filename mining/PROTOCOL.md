# Code-study protocol (M1 and M2), frozen 8 October 2026

Frozen before any study item was coded. Codebook: `mining/CODEBOOK.md` (version 1.0, same date; version 1.1 from 8 October, see below). Later changes are recorded at the end with their date and reason.

## M1: failure-handling sites inside the libraries

**Question.** Through which channel does each library hand a failed PACE, BAC, Chip Authentication, Active Authentication or secure-messaging step to its caller?

**Population.** Batch 1 is `mining/m1-sites.csv` at harness commit `e7dc4d7`: 534 sites in gmrtd (three releases), JMRTD 0.8.9, emrtd-dotnet, dmrtd and NFCPassportReader, listed by `mining/m1_sites.py` (patterns and files in scope are in the script). Batch 2 adds the WebAuthn relying-party libraries with the same script, extended only by their file scope and the same pattern families; it is listed and frozen before batch 2 is coded.

**Coding.** Coder A codes every site. Coder B codes a random 30 per cent of each batch, drawn with `random.Random(20261008)` over the sorted site IDs. Neither coder runs the code or looks at the dynamic results while coding.

## M2: application call sites

**Question.** When an embedded eMRTD library reports, or fails to report, a PACE, CA or AA failure, what does the application do with it?

**Sources.** GitHub code search through the API, all queries run on one date (recorded in `mining/m2/raw/DATE`), raw results saved in `mining/m2/raw/`:

| Library | Queries |
| --- | --- |
| JMRTD (Java) | `doPACE language:java` |
| JMRTD (Kotlin) | `doPACE language:kotlin`; `PACEException language:kotlin`; `org.jmrtd language:kotlin` |
| NFCPassportReader (Swift) | `import NFCPassportReader language:swift`; `PACEStatus NFCPassportReader` |
| dmrtd (Dart) | `package:dmrtd language:dart`; `startSessionPACE language:dart` |
| gmrtd (Go) | `github.com/gmrtd/gmrtd language:go` |
| emrtd-dotnet (C#) | `Emrtd DocumentReader language:csharp` |

Plus the fork network of `tananaev/passport-reader` and each library's GitHub dependents page.

**Inclusion.** A repository is included if it is application code that calls a PACE, CA, AA or document-read API of one of the libraries.

**Exclusion**, applied in this order, each counted and reported:
1. The library itself, its forks without application code, and vendored copies of the library.
2. Forks of an included application with no change to the call site (counted under lineage instead).
3. Tutorials, snippets and templates with under 50 lines of logic outside the library call.
4. Clients that use only BAC (no PACE, CA or AA call).
5. Repositories whose call site cannot be located in the default branch.

**Sampling.** The unit is one call site; a repository contributes at most one call site per step. A library with 40 or fewer eligible call sites is coded in full; otherwise 40 are drawn with `random.Random(20261004)` over the sorted call-site IDs.

**Coding.** As for M1: coder A codes every call site, coder B a random 30 per cent (`random.Random(20261008)`).

## Agreement and adjudication

Cohen's kappa with a 95 per cent confidence interval per variable and batch (`mining/kappa.py`). Target 0.7; a variable below 0.6 has its definition reviewed and both coders recode it, and that review is recorded below. Every disagreement is settled by discussion and logged in `mining/adjudication-log.md`.

## Ethics

Public code only. Applications whose handling would let a document be accepted after a failed authentication are reported in aggregate or under anonymous identifiers; maintainers of actively maintained affected applications are told before publication; the identifiable list is kept private and is available to reviewers on request.

## Changes after freezing

1. **8 October 2026, codebook v1.1, before any study item was coded.** Reason: coder B's review of v1.0. Wording shortened and process text moved here; decision rules added for channel (immediate-caller definition with a fixed order for genuine ties), CONVERT, LOG versus SWALLOW, continues, fallback, reaches_api (LOG is INDIRECT only when the caller can attach the logger through the public API), PROPAGATE versus IGNORE (an uncaught exception is PROPAGATE), NA (established from library source), user_visible_accept (control flow, bounded trace, UNCLEAR otherwise) and lineage (evidence required). Added: the value NOT_A_SITE for M1 rows that are not decision points; a closed misuse_class list from MUC (Amann et al. 2019); required evidence_note; constructed examples for M1 and M2 in place of examples from study libraries, so that no study item appears in the codebook with its answer; passauf in the library list (sixth library, added the same day). No category was removed. Both coders recode the 10 calibration items with v1.1 before study coding.
