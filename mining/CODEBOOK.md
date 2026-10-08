# Codebook v1.1: failure reporting in eMRTD libraries (M1) and their applications (M2)

Process, sampling and agreement rules are in the code-study protocol (`PROTOCOL.md`, shipped with this codebook). This page is what a coder keeps open while coding.

**Three rules.** Code what the code does at the pinned commit, not what its documentation says. When unsure, pick the closest value, tick `uncertain` and write one line why. Do not run the code or look at the dynamic results.

**Every row.** Location columns are filled in for you. You fill the variables, `evidence_note` (required: file:line and what happens, one line), `uncertain` and `uncertainty_note`.

## M1: failure sites inside the libraries

**Unit.** One row of `m1-sites.csv`: one source location where the library decides what to do with a failure. Do not split or merge rows; nested sites are separate rows. If the row is not such a decision point, code `NOT_A_SITE` in `step` and give the reason.

| Variable | Ask | Values |
| --- | --- | --- |
| step | Which protocol step failed? | PACE, BAC, CA, AA, TA, SM (secure messaging), FILE (select or read), PA (passive authentication), OTHER, NOT_A_SITE |
| channel | How is the failure made available to the immediate caller? | THROW: an exception or panic reaches the caller. RETURN: an error value or failure result is returned. STATUS: the caller must read a field or object. CONVERT: the failure becomes a value the caller would read as successful data. LOG: only a logger or callback records it. SWALLOW: no failure indication in the API and not logged. |
| continues | Does the enclosing operation go on? | YES: execution proceeds within the enclosing authentication or read operation (at the last step: the operation still produces a result). NO: the operation ends because of the failure. |
| fallback | Is a recovery path started? | BAC: a PACE failure leads to a BAC attempt. RETRY: the same step is tried again. OTHER: another path started explicitly as recovery. NONE. |
| reaches_api | Can the caller of the public read or authenticate call see it? | DIRECT: in the return value, a thrown exception or the directly returned result of that call. INDIRECT: the call completes normally and the caller must inspect another object, field, callback or log. NO: nothing the caller can reach. |

**Decision rules.**
1. A success return is not RETURN. Setting `session.PaceErr` and returning `nil` as the error is STATUS.
2. Only if two mechanisms both carry the failure, take the first of THROW, RETURN, STATUS, CONVERT, LOG, SWALLOW, and name the other in the note.
3. CONVERT only when the API's meaning makes the value indistinguishable from success: an empty array returned as response data is CONVERT; `nil` documented as "no result" is RETURN.
4. LOG is INDIRECT when the caller can attach the logger or callback through the public API, otherwise NO.
5. A THROW site is `continues` NO unless the same site catches it.
6. Ordinary continuation to the next step is not a fallback.

**Examples** (constructed; not taken from any library in the study).

| Site | step | channel | continues | fallback | reaches_api |
| --- | --- | --- | --- | --- | --- |
| `if err != nil { s.lastErr = err; return s.readWithBAC() }`, and the read function returns no error | PACE | STATUS | YES | BAC | INDIRECT |
| `if !ok { throw AuthException("PACE failed") }` inside the public `authenticate()` | PACE | THROW | NO | NONE | DIRECT |
| `catch (e) { logger.warn(e); continue }` with the logger set by the caller through the public API | CA | LOG | YES | NONE | INDIRECT |
| `if (sw != 0x9000) return new byte[0];` where the caller treats the bytes as the signature | AA | CONVERT | YES | NONE | NO |
| `catch (e) { }` and the next step runs | SM | SWALLOW | YES | NONE | NO |

## M2: application call sites

**Unit.** One call site from the M2 list: a place where an application calls a library's PACE, CA, AA or document-read API, or reads its result.

| Variable | Ask | Values |
| --- | --- | --- |
| library | Which library is called? | gmrtd, JMRTD, emrtd-dotnet, dmrtd, NFCPassportReader, passauf, OTHER |
| step | Which step does the call cover? | PACE, CA, AA, READ (whole-document read) |
| handling | What does the application's own code do with a failure? | PROPAGATE: the failure leaves the application-level operation and reaches a caller, the user or an error boundary (an uncaught exception counts). CHECK: the application reads the status or result and acts on a failure. LOG_CONTINUE: it catches or notes the failure, logs it and carries on. IGNORE: a failure indication is available but the application never inspects it and proceeds as on success. NA: see rule 3. |
| user_visible_accept | Can the failure still end in "document read and valid"? | YES: control flow shows the success outcome is reachable after the failure. NO: control flow shows the failure prevents it. UNCLEAR: the source does not establish either. |
| misuse_class | Which MUC category fits? | One code from the list below. |
| lineage | Where does this code come from? | ORIGINAL; FORK_OF(repo); COPIED_FROM(repo) |

**Decision rules.**
1. Code what the application's code does. If an exception escapes into framework code (for example an Android executor), code PROPAGATE and name the framework in the note.
2. Do not infer YES for `user_visible_accept` from a missing check. Trace within the repository up to the result or UI handler; if it goes further, UNCLEAR.
3. NA only when the library source at the pinned version shows that the called API gives no failure indication for this step at this call site; never because the application does not check.
4. FORK_OF from GitHub fork metadata or history; COPIED_FROM only with evidence (attribution, or identical files with history). Never from similarity alone.

**misuse_class** (API-Misuse Classification, MUC: Amann et al., TSE 2019, Table 2 and Section 3.2).

| Code | Meaning |
| --- | --- |
| MISSING_CALL | A call the API requires is absent (e.g. never calling the authentication step) |
| REDUNDANT_CALL | A call the API forbids or makes unnecessary is present |
| MISSING_NULL_CHECK / REDUNDANT_NULL_CHECK | A required null check is absent / a null check prevents a needed call or is pointless |
| MISSING_VALUE_OR_STATE / REDUNDANT_VALUE_OR_STATE | A required check of a value or state is absent (e.g. a status field never read) / a check blocks a needed part or is pointless |
| MISSING_SYNC / REDUNDANT_SYNC | A required lock is absent / a lock is taken again or unnecessarily |
| MISSING_CONTEXT / REDUNDANT_CONTEXT | A required execution context (e.g. thread) is not ensured / code runs in a context where it cannot work |
| MISSING_ITERATION / REDUNDANT_ITERATION | A required repetition is absent / a part that must run once is repeated |
| MISSING_EXCEPTION_HANDLING | The application takes no action on an error the API reports |
| REDUNDANT_EXCEPTION_HANDLING | The application intercepts an exception it should not catch or suppress |
| NONE | No category applies |

**Examples** (constructed; not taken from any repository in the study).

| Call site | handling | user_visible_accept | misuse_class |
| --- | --- | --- | --- |
| `try { doPace() } catch (e: Exception) { log(e) }`, then BAC and the document is shown | LOG_CONTINUE | YES | REDUNDANT_EXCEPTION_HANDLING |
| `readPassport()` with no catch; the screen's error handler shows "read failed" | PROPAGATE | NO | NONE |
| `if (result.paceStatus == FAILED) reject()` before the document is shown | CHECK | NO | NONE |
| The document is shown and `result.paceStatus` is never read | IGNORE | YES | MISSING_VALUE_OR_STATE |
