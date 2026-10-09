#!/usr/bin/env python3
"""M2 step 2: screening (exclusions 1 to 5 of mining/PROTOCOL.md, in order) and call-site location.

Input: candidates.csv (step 1). For every repository: its metadata (gh api repos/...), the commit at the head
of its default branch, and each candidate file at that commit (raw.githubusercontent.com). Every fetched
response is cached under screen/cache/ so the screening can be rerun offline and checked.

Rules as implemented (each written so that it needs no judgement; PROTOCOL.md change 3):
  E1  library itself, its forks, vendored copies: the repository is a library repository or a fork of one
      (or this study's own harness, whose drivers call the libraries as tests);
      or a candidate file lies inside a copy of a library's own source (LIB_PATH). A repository is excluded
      when none of its candidate files remains.
  E2  forks of an included application with no change to the call site: the repository is a fork (metadata)
      and its call-site lines equal its parent's at the parent's default branch.
  E3  tutorials, snippets and templates: the repository's source files in the library's language, outside
      library copies, hold fewer than 50 logic lines (non-blank, non-comment). Counted from the git tree:
      a repository whose such files total 8,000 bytes or more is above the threshold without counting.
  E4  BAC-only clients: no candidate file calls a PACE, CA, AA or document-read API of the library
      (CALLS); a call whose options turn PACE, CA and AA off counts as BAC-only.
  E5  call site not locatable: no candidate file exists at the head of the default branch and no call is found
      in the repository's other source files.
  not_included: the repository calls no PACE, CA, AA or document-read API in any source file (inclusion
      criterion; for example a repository that uses the library only to parse or verify document data).
  Calls are searched in the candidate files and, when those hold none, in every other source file of the
  library's language outside library copies (at most 400 per repository, in path order).
Call sites: one per (repository, library, step), step in PACE, CA, AA, READ; the first matching line in the
first candidate file in path order. ID = M2-<library>-<n>, numbered over the sorted (library, repo, step).
Usage: python mining/m2/screen_m2.py [--workers 8]   (needs an authenticated gh)
Writes: screen/screen.csv (one row per repository with the exclusion or "included"), screen/m2-callsites.csv,
        screen/SUMMARY.json
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "screen"
CACHE = OUT / "cache"

LIB_REPOS = {
    "jmrtd": {"jmrtd/jmrtd", "E3V3A/JMRTD"},
    "nfcpassportreader": {"AndyQ/NFCPassportReader"},
    "dmrtd": {"ZeroPass/dmrtd"},
    "gmrtd": {"gmrtd/gmrtd"},
    "emrtd-dotnet": {"chamnan/emrtd-dotnet"},
}
# The study's own repositories call the libraries as test drivers, not as applications.
STUDY_REPOS = {"kazuru-chidumbwe/caller-boundary-oracle", "kazuru-chidumbwe/emrtd-differential-harness"}
# A candidate file inside a copy of the library's own source tree is a vendored copy, not a call site.
LIB_PATH = {
    "jmrtd": r"(^|/)org/jmrtd/",
    "nfcpassportreader": r"(^|/)Sources/NFCPassportReader/|(^|/)NFCPassportReader/(PassportReader|TagReader|PACEHandler|ChipAuthenticationHandler)\.swift$",
    "dmrtd": r"(^|/)dmrtd/lib/|(^|/)lib/src/(proto|lds|com)/",
    "gmrtd": r"(^|/)gmrtd/(pace|bac|chipauth|activeauth|iso7816|reader|mobile|passiveauth|document)/",
    "emrtd-dotnet": r"(^|/)src/Emrtd/",
}
LANG_EXT = {"jmrtd": (".java", ".kt"), "nfcpassportreader": (".swift",), "dmrtd": (".dart",),
            "gmrtd": (".go",), "emrtd-dotnet": (".cs",)}
# Calls an application makes; READ is a document-read API that runs the protocols inside.
CALLS = {
    "jmrtd": [("PACE", r"\bdoPACE\s*\("), ("CA", r"\bdo(EAC)?CA\s*\("), ("AA", r"\bdoAA\s*\(")],
    "nfcpassportreader": [("READ", r"\breadPassport\s*\(")],
    "dmrtd": [("PACE", r"\bstartSessionPACE\s*\("), ("AA", r"\bactiveAuthenticate\s*\(")],
    "gmrtd": [("READ", r"\.ReadDocument\s*\(")],
    "emrtd-dotnet": [("READ", r"\bDocumentReader\b.*\.Read\s*\(|\.Read\s*\(.*\bReadOptions\b")],
}
# Options that switch PACE, CA and AA off make a READ call BAC-only (E4).
BAC_ONLY = {
    "nfcpassportreader": lambda text: bool(re.search(r"skipPACE\s*:\s*true", text)) and bool(re.search(r"skipCA\s*:\s*true", text)),
    "emrtd-dotnet": lambda text: bool(re.search(r"UsePace\s*=\s*false", text)),
}
COMMENT = {".java": "//", ".kt": "//", ".swift": "//", ".dart": "//", ".go": "//", ".cs": "//"}


def gh(path: str) -> dict | list | None:
    key = CACHE / "api" / (hashlib.sha256(path.encode()).hexdigest() + ".json")
    if key.exists():
        return json.loads(key.read_text(encoding="utf-8"))
    for attempt in range(6):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0 or not path.startswith("search/"):
            break
        time.sleep(65)   # code search rate limit: wait for the next window
    data = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    if data is None and path.startswith("search/"):
        return None      # a failed search is never cached
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps({"path": path, "data": data}), encoding="utf-8")
    return data if data is not None else None


def gh_cached(path: str):
    key = CACHE / "api" / (hashlib.sha256(path.encode()).hexdigest() + ".json")
    if key.exists():
        return json.loads(key.read_text(encoding="utf-8"))["data"]
    return gh(path)


def raw(repo: str, sha: str, path: str) -> str | None:
    key = CACHE / "raw" / (hashlib.sha256(f"{repo}@{sha}:{path}".encode()).hexdigest() + ".txt")
    miss = key.with_suffix(".missing")
    if key.exists():
        return key.read_text(encoding="utf-8", errors="replace")
    if miss.exists():
        return None
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/" + urllib.request.quote(path)
    key.parent.mkdir(parents=True, exist_ok=True)
    text = None
    for attempt in range(12):   # 5xx and network errors are transient on raw.githubusercontent.com
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                text = r.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                miss.write_text("404")
                return None
            if attempt == 11:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 11:
                raise
        time.sleep(min(60, 2 ** attempt))
    key.write_text(text, encoding="utf-8")
    return text


def logic_lines(text: str, ext: str) -> int:
    n, block = 0, False
    for line in text.splitlines():
        s = line.strip()
        if block:
            if "*/" in s:
                block = False
            continue
        if not s or s.startswith(COMMENT[ext]) or s.startswith("*"):
            continue
        if s.startswith("/*"):
            block = "*/" not in s
            continue
        n += 1
    return n


def screen_repo(repo: str, rows: list[dict]) -> dict:
    """Compute every test first, then give the first exclusion that applies, in the protocol's order."""
    lib = rows[0]["libraries"].split(";")[0]
    res = {"repo": repo, "library": lib, "candidate_files": len(rows)}
    if repo in STUDY_REPOS:
        return {**res, "decision": "E1", "reason": "the study's own harness (test drivers, not an application)"}
    meta = gh_cached(f"repos/{repo}")
    if not meta:
        return {**res, "decision": "E5", "reason": "repository not reachable"}
    branch = meta.get("default_branch")
    head = gh_cached(f"repos/{repo}/commits/{branch}")
    sha = head.get("sha") if isinstance(head, dict) else None
    res.update(default_branch=branch, head_sha=sha, fork=meta.get("fork"),
               parent=(meta.get("parent") or {}).get("full_name"))
    # E1
    if repo in LIB_REPOS[lib] or res["parent"] in LIB_REPOS[lib]:
        return {**res, "decision": "E1", "reason": "library repository or fork of it"}
    files = [r for r in rows if not re.search(LIB_PATH[lib], r["path"])]
    if not files:
        return {**res, "decision": "E1", "reason": "every candidate file is inside a copy of the library source"}
    if not sha:
        return {**res, "decision": "E5", "reason": "default branch head not readable"}
    tree = gh_cached(f"repos/{repo}/git/trees/{sha}?recursive=1")
    blobs = [b for b in (tree or {}).get("tree", []) if b.get("type") == "blob"
             and b["path"].endswith(LANG_EXT[lib]) and not re.search(LIB_PATH[lib], b["path"])]
    # call sites at the head of the default branch: the candidate files first, then (if they hold no call)
    # every other source file of the library's language in the repository, outside library copies
    texts = {}
    for r in sorted(files, key=lambda r: r["path"]):
        t = raw(repo, sha, r["path"])
        if t is not None:
            texts[r["path"]] = t
    candidates_at_head = bool(texts)

    def find_sites(tx: dict) -> dict:
        found = {}
        for path in sorted(tx):
            for no, line in enumerate(tx[path].splitlines(), 1):
                for step, rx in CALLS[lib]:
                    if step not in found and re.search(rx, line) and not line.strip().startswith("//"):
                        found[step] = {"path": path, "line": no, "code": line.strip()[:200]}
        return found
    sites = find_sites(texts)
    res["searched"] = "candidate files"
    if not sites:
        others = sorted(b["path"] for b in blobs if b["path"] not in texts)
        res["searched"] = f"candidate files + {min(len(others), 400)} of {len(others)} other source files"
        for path in others[:400]:
            t = raw(repo, sha, path)
            if t is not None:
                texts[path] = t
        sites = find_sites(texts)
        if not sites and len(others) > 400 and lib == "jmrtd":
            # past the cap: repo-scoped code search finds the files that name a call (PROTOCOL change 3)
            found = set()
            for term in ("doPACE", "doCA", "doEACCA", "doAA", "doBAC"):
                q = f"search/code?q={term}+repo:{repo}&per_page=100"
                key = CACHE / "api" / (hashlib.sha256(q.encode()).hexdigest() + ".json")
                if not key.exists():
                    time.sleep(2.2)   # code search allows 30 requests a minute
                for it in (gh_cached(q) or {}).get("items", []):
                    if it["path"].endswith(LANG_EXT[lib]) and not re.search(LIB_PATH[lib], it["path"]):
                        found.add(it["path"])
            res["searched"] += f" + {len(found)} from repo code search"
            for path in sorted(found - set(texts)):
                t = raw(repo, sha, path)
                if t is not None:
                    texts[path] = t
            sites = find_sites(texts)
    # E2: fork whose call-site lines equal the parent's
    e2 = False
    if res["fork"] and res["parent"] and sites:
        pmeta = gh_cached(f"repos/{res['parent']}")
        phead = gh_cached(f"repos/{res['parent']}/commits/{pmeta.get('default_branch')}") if pmeta else None
        psha = phead.get("sha") if isinstance(phead, dict) else None
        e2 = bool(psha) and all((raw(res["parent"], psha, x["path"]) or "").splitlines()[x["line"] - 1:x["line"]] == [x["code"]]
                                for x in sites.values())
    # E3: logic lines in the library's language outside library copies
    total = sum(b.get("size", 0) for b in blobs)
    if total < 8000:
        lines = sum(logic_lines(texts.get(b["path"]) or raw(repo, sha, b["path"]) or "", "." + b["path"].rsplit(".", 1)[-1])
                    for b in blobs)
        res["logic_lines"] = lines
    else:
        lines = None
        res["logic_lines"] = f">= 50 ({total} bytes)"
    bac = any(re.search(r"doBAC|startSession\s*\(|BACKey|DBAKey", t) for t in texts.values())
    bac_only_opts = bool(sites) and lib in BAC_ONLY and all(BAC_ONLY[lib](texts[x["path"]]) for x in sites.values())
    if e2:
        return {**res, "decision": "E2", "reason": f"fork of {res['parent']} with the same call-site lines"}
    if lines is not None and lines < 50:
        return {**res, "decision": "E3", "reason": f"{lines} logic lines in {len(blobs)} source files"}
    if (not sites and bac) or bac_only_opts:
        return {**res, "decision": "E4", "reason": "only BAC calls" if not sites else "read call with PACE, CA and AA switched off"}
    if not candidates_at_head and not sites:
        return {**res, "decision": "E5", "reason": "no candidate file at the head of the default branch, no call elsewhere"}
    if not sites:
        return {**res, "decision": "not_included", "reason": "no PACE, CA, AA or document-read call in the repository"}
    res["sites"] = sites
    return {**res, "decision": "included", "reason": ""}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    by_repo = defaultdict(list)
    with (HERE / "candidates.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_repo[r["repo"]].append(r)
    OUT.mkdir(exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(lambda kv: screen_repo(*kv), sorted(by_repo.items())))
    with (OUT / "screen.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["repo", "library", "candidate_files", "default_branch", "head_sha", "fork",
                                          "parent", "searched", "logic_lines", "decision", "reason"], extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    sites = []
    for r in results:
        for step, s in sorted((r.get("sites") or {}).items()):
            sites.append({"library": r["library"], "repo": r["repo"], "step": step, "commit": r["head_sha"],
                          "file": s["path"], "line": s["line"], "code": s["code"],
                          "url": f"https://github.com/{r['repo']}/blob/{r['head_sha']}/{s['path']}#L{s['line']}"})
    sites.sort(key=lambda s: (s["library"], s["repo"], s["step"]))
    n = Counter()
    for s in sites:
        n[s["library"]] += 1
        s["callsite_id"] = f"M2-{s['library']}-{n[s['library']]:04d}"
    with (OUT / "m2-callsites.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["callsite_id", "library", "repo", "step", "commit", "file", "line", "code", "url"])
        w.writeheader()
        w.writerows(sites)
    summary = {"repositories": len(results),
               "by_decision": dict(Counter(r["decision"] for r in results)),
               "by_library_decision": {f"{k[0]} {k[1]}": v for k, v in
                                       sorted(Counter((r["library"], r["decision"]) for r in results).items())},
               "call_sites": len(sites), "call_sites_by_library": dict(n),
               "call_sites_by_library_step": dict(Counter(f"{s['library']} {s['step']}" for s in sites))}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
