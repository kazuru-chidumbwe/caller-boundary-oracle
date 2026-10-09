#!/usr/bin/env bash
# Testbed A, unattended (9 Oct 2026): T56 check, then T5b.
#  1. build and test at the DG2 commit (make test)
#  2. T56 check evaluation: every suite at the DG2 commit. A CHECK that expectations hold with DG2
#     served; not the final evaluation (T55), whose single run produces the paper's numbers.
#  3. T5b: secure-messaging mutants (design D5 side table), run on the CA and AA cells, scored.
# Progress: ~/cbo/lab-chain.progress. Stop: kill $(cat ~/cbo/lab-chain.pid)
set -uo pipefail
# 9 Oct 10:05: rerun after the first pass (evaluate stopped at pace on the 7 known passauf cells; dmrtd driver path).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
P=~/cbo/lab-chain.progress
echo $$ > ~/cbo/lab-chain.pid
st() { echo "[$(date -u +%H:%M:%S)] $*" >> "$P"; }
PATH="/usr/local/go/bin:$PATH"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then PATH="$ROOT/.venv/bin:$PATH"; fi
export PATH GOTOOLCHAIN=local
st "start: harness $(git rev-parse --short HEAD)"

if make test > ~/cbo/chain-test.log 2>&1; then st "tests pass"; else st "TESTS FAILED (chain-test.log): stopped"; exit 1; fi

# One suite per call: evaluate.sh stops at the first suite with a mismatch, and the pace suite holds the
# seven passauf held-out cells whose pre-registered expectation was not met (run f1553f2). Those seven are
# the expected mismatches; any other mismatch is a change.
for suite in ${CHECK_SUITES:-pace ca-aa controls independent independent-repeat}; do
  if SUITES=$suite bash scripts/evaluate.sh > ~/cbo/chain-evaluate-$suite.log 2>&1; then
    st "T56 check $suite: all entries verify"
  else
    st "T56 check $suite: $(grep -c '^VERIFY FAIL' ~/cbo/chain-evaluate-$suite.log) mismatches, of which not passauf: $(grep '^VERIFY FAIL' ~/cbo/chain-evaluate-$suite.log | grep -vc passauf) (chain-evaluate-$suite.log)"
  fi
done

mkdir -p ../sm-side
if python3 mutation/make_mutants.py --vendor ../_vendor --steps SM --out ../sm-side > ~/cbo/chain-sm-make.log 2>&1; then
  st "T5b mutants: $(head -1 ~/cbo/chain-sm-make.log)"
else
  st "T5b generator FAILED (chain-sm-make.log): stopped"; exit 1
fi
if bash mutation/run.sh --mutants ../sm-side/mutants.jsonl --out ../mutruns-sm > ~/cbo/chain-sm-run.log 2>&1; then
  st "T5b runs done"
else
  st "T5b runs stopped (chain-sm-run.log; tail of ../mutruns-sm/progress.log)"; exit 1
fi
python3 mutation/score.py --runs ../mutruns-sm/runs --out ../sm-side/out > ~/cbo/chain-sm-score.log 2>&1 \
  && st "T5b scored (~/cbo/sm-side/out)" || st "T5b scoring FAILED (chain-sm-score.log)"
st "LAB CHAIN ALL DONE"
