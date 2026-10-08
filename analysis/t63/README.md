# T63: D5 across all gmrtd releases

D5 is the ECDH shared secret taken as `x.Bytes()`, which drops leading zero bytes instead of encoding the field element at field size (BSI TR-03111 FE2OS). This folder checks every gmrtd release for it with one deterministic test.

## Test

`zz_t63_leading_zero_test.go` is copied into the `chipauth` package of each release and run there (`go test ./chipauth -run TestT63`). It calls that release's own `deriveSessionKeys` with:

- chip key G on P-256;
- terminal private key d = 379, the smallest scalar whose shared x-coordinate has a leading zero byte (31 bytes).

It then compares the release's session key ksEnc with the KDF of the secret in two encodings, at field size (32 bytes) and short (31 bytes):

| Verdict | Meaning |
| --- | --- |
| `D5_PRESENT` | ksEnc equals the short form and not the field-size form |
| `D5_ABSENT` | ksEnc equals the field-size form |
| `OTHER` | anything else |

`run.sh` exports each tag with `git archive`, adds only the test file, and runs it. It also runs a control: v1.3.2 with the drafted fix (`fix-control.patch`, same as `s1-emrtd/upstream/gmrtd-ecdh-shared-secret-length.patch`) applied.

The test reaches the Chip Authentication call site. The two PACE call sites (`pace.go`, key agreement and evidence verification) take the secret as `termShared.X.Bytes()` and `kaShared.X.Bytes()` in every release; this was checked in the source with `git grep` on each tag.

## Result (8 Oct 2026, Testbed A)

Run on Testbed A, from the gmrtd clone with tags up to v1.3.3. The Go toolchain is the one each release's `go.mod` requests, selected through `GOTOOLCHAIN=auto` from base go1.24.4 (go1.25.0 and go1.26.x). `out/t63.tsv` holds the result line of every release; the per-release logs stay on Testbed A (`~/cbo/t63/out`), because the repository ignores `*.log`.

| Releases | Verdict |
| --- | --- |
| v0.40.0 to v1.3.2 (29 releases; all of the version sweep) | D5_PRESENT in all 29 |
| v1.3.3 (released after the sweep) | D5_PRESENT |
| v1.3.2 + drafted fix (control) | D5_ABSENT |

The seven releases before 0.45.0 do not build with the unchanged harness driver (VERSION-SWEEP.md). Their `chipauth` package compiles and runs this test, so D5 is measured for them too.
