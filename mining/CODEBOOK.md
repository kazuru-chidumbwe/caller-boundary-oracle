# Codebook v1.0: failure reporting in eMRTD reader libraries (M1) and their integrators (M2)

Frozen 8 October 2026 after the calibration session: both coders agreed version 0.1 without changes, so 1.0 is identical in content. Two coders: coder A (the author) and coder B (not an author). Published with the artifact; not changed after this date.

## How coding works

1. **Calibration (about 2 hours together).** Both coders read this codebook, then code 10 practice items (not part of the study) side by side and discuss every difference. Definitions are tightened where the difference came from wording. The codebook becomes v1.0 and is not changed after this point.
2. **Independent coding.** Each coder codes the study items alone, in a spreadsheet, without seeing the other's labels. Coder B codes either all items (preferred) or a random sample of at least 30% drawn with a fixed seed.
3. **Agreement.** Cohen's kappa per variable, computed by a script in the repo. Target: kappa of at least 0.7 per variable; below 0.6, the variable's definition is revised and both coders recode it.
4. **Adjudication.** Disagreements are discussed and settled; every case and its resolution goes into an adjudication log (published).
5. **Rules for both coders.**
   - Code what the code does at the pinned commit, not what the documentation says.
   - When unsure, pick the closest label, tick "uncertain", and write one line why.
   - Do not run the code or look at the dynamic results (RQ2) while coding.

## M1: failure-reporting sites inside the libraries

**Unit:** one site in a library's source where a protocol step's failure is detected and handed on (or not). A site is the line where the library decides what to do with a failure: throw, return an error, set a field, log, or drop it.

**Population:** every such site for the steps below, in gmrtd (3 pinned versions), JMRTD 0.8.9, emrtd-dotnet, dmrtd and NFCPassportReader at their pinned commits. Sites are listed by coder A with a reproducible search (patterns published); coders label them, they do not search.

### M1 variables

| Variable | Values |
| --- | --- |
| step | PACE, BAC, CA, AA, TA, SM (secure messaging), FILE (file select/read), PA (passive authentication), OTHER |
| channel | THROW: raises an exception or panics to the caller<br>RETURN: returns an error value or failure result<br>STATUS: writes the failure into a field or object the caller can read (e.g. `Session.PaceErr`, `PACEStatus = .failed`)<br>LOG: only logs it (logger, callback, print)<br>SWALLOW: drops it with no trace reachable by the caller<br>CONVERT: turns it into a different success-looking value (e.g. empty array returned as data) |
| continues | YES if execution carries on with the next protocol step after the failure; NO if the operation stops |
| fallback | NONE, BAC (falls back to BAC), RETRY, OTHER |
| reaches_api | DIRECT if the channel is visible at the library's public read/authenticate call; INDIRECT if the caller must inspect something else (a field, a log callback); NO |
| uncertain | tick + one-line note |

### M1 examples (from the pinned code; for calibration, not study items)

| Site | step | channel | continues | fallback | reaches_api |
| --- | --- | --- | --- | --- | --- |
| gmrtd 0.45.0 `performPace` records the PACE error in the session and returns nil | PACE | STATUS | YES | BAC | INDIRECT |
| JMRTD `PassportService.doPACE` throws `PACEException` | PACE | THROW | NO | NONE | DIRECT |
| NFCPassportReader `PassportReader` catch: `passport.PACEStatus = .failed`, log "falling back to BAC" | PACE | STATUS | YES | BAC | INDIRECT |
| NFCPassportReader `TagReader.send`: `if sw1 != 0x90 && sw2 != 0x00` (6F00 passes as success) | SM | CONVERT | YES | NONE | NO |
| JMRTD `AAAPDUSender.sendInternalAuthenticate` returns response data for any status word | AA | CONVERT | YES | NONE | NO |

## M2: integrator call sites in applications

**Unit:** one place in an application's source where it calls a library's read or authentication API (or reads its result) and must decide what to do if that step failed.

**Population:** repositories found by the pre-registered search (queries, dates and inclusion rules published in the protocol), from the seed tananaev/passport-reader, fork-network traversal, and per-library code search.

**Inclusion:** application code (not the library itself, not vendored copies, not unmodified forks); at least one call to a PACE, CA, AA or document-read API of the five libraries. **Exclusion:** tutorials and snippets under 50 lines of logic, BAC-only clients, archived templates with no app logic.

### M2 variables

| Variable | Values |
| --- | --- |
| library | gmrtd, JMRTD, emrtd-dotnet, dmrtd, NFCPassportReader, OTHER |
| step | PACE, CA, AA, READ (whole-document read) |
| handling | PROPAGATE: the failure stops the flow or reaches the user as an error<br>CHECK: the app reads the status field or result and acts on a failure<br>LOG_CONTINUE: catches or notes the failure, logs it, carries on<br>IGNORE: never looks at the failure (no catch, no status read; continues on success path)<br>NA: the library cannot fail this step in a way the app could see |
| user_visible_accept | YES if, on that failure, the app would still show the document as read and valid; NO; UNCLEAR |
| misuse_class | MUBench category where it fits (e.g. missing condition check, missing exception handling); otherwise NONE |
| lineage | ORIGINAL, FORK_OF(<repo>), COPIED_FROM(<repo or sample>) |
| uncertain | tick + one-line note |
