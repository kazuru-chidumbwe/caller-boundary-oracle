# T13 result: consequence demo (JMRTD SampleReader)

Harness 46ef67e (clean before and after); JMRTD 0.8.9; harness chip (`cmd/chip-serve`, `-trusted-chain` for R2 and R4);
Testbed A, 5 Nov 2026. Runs and expectations in `examples/t13-consequence/expectations.json`, committed before the run
(a0b1068; R2 and R4 marked trusted-chain in 46ef67e after the first run was archived as a runner fault, see below).
All four runs as expected.

| run | chip | app | AA answer (trace) | doAA | AAResult response | app shows |
| --- | --- | --- | --- | --- | ---: | --- |
| R1 | refuses AA (6982 under SM) | common pattern | `99 02 6982 8E08 ...` | returns | 0 bytes | authentic = true |
| R2 | signs (trusted chain) | common pattern | 128-byte signature, 9000 | returns | 128 bytes | authentic = true |
| R3 | refuses AA (6982 under SM) | defensive (non-empty check) | `99 02 6982 8E08 ...` | returns | 0 bytes | authentic = false |
| R4 | signs (trusted chain) | defensive | 128-byte signature, 9000 | returns | 128 bytes | authentic = true |

The application written in the common pattern shows a document whose chip refused Active Authentication as
authentic (R1). The same application with a one-line check of the returned response rejects it (R3) and still
accepts a chip that signs (R4).

Archived run: the first run (a0b1068, 20261105T201119Z) used chip-serve without a trusted-chain mode; the
AA-success profile then answered INTERNAL AUTHENTICATE with 6D00, so R2 and R4 had no working AA chip (R4 showed
authentic = false; R2 passed only because the pattern accepts the 6D00 refusal too). chip-serve gained
`-trusted-chain` (as gmrtd-read), the expectations now also require a non-empty response for R2 and R4, and the
demo was rerun from scratch.

Figure 7: `figure-7-consequence.png` / `.pdf` (`analysis/figure_t13.py`, from R1, R3, R2).
