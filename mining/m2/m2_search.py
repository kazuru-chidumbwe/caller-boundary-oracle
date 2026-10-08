#!/usr/bin/env python3
"""M2 step 1: run the frozen code-search queries (mining/PROTOCOL.md) and list candidate call-site files.

Every query is run through `gh api search/code` on one date (written to raw/DATE); every result
page is saved under raw/. The output candidates.csv has one row per (repository, file) with the
library it was found for, the repository's fork flag, and the query that found it. Screening
(exclusions 1 to 5) and call-site location follow in screen_m2.py.

Usage: python mining/m2/m2_search.py   (needs an authenticated gh)
"""

from __future__ import annotations

import csv
import datetime
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUERIES = [
    ("jmrtd", "doPACE language:java"),
    ("jmrtd", "doPACE language:kotlin"),
    ("jmrtd", "PACEException language:kotlin"),
    ("jmrtd", "org.jmrtd language:kotlin"),
    ("nfcpassportreader", "import NFCPassportReader language:swift"),
    ("nfcpassportreader", "PACEStatus NFCPassportReader"),
    ("dmrtd", "package:dmrtd language:dart"),
    ("dmrtd", "startSessionPACE language:dart"),
    ("gmrtd", "github.com/gmrtd/gmrtd language:go"),
    ("emrtd-dotnet", "Emrtd DocumentReader language:csharp"),
]
PAGES = 10  # the search API returns at most 1,000 results per query


def search(q: str, page: int) -> dict:
    for attempt in range(5):
        p = subprocess.run(["gh", "api", "-X", "GET", "search/code", "-f", f"q={q}", "-f", "per_page=100",
                            "-f", f"page={page}"], capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0:
            return json.loads(p.stdout)
        if "rate limit" in (p.stderr + p.stdout).lower() or "secondary" in (p.stderr + p.stdout).lower():
            time.sleep(65)
            continue
        raise SystemExit(f"search failed for {q!r} page {page}: {p.stderr[:300]}")
    raise SystemExit(f"search kept hitting the rate limit for {q!r}")


def main() -> None:
    raw = HERE / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "DATE").write_text(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ") + "\n")
    rows: dict[tuple, dict] = {}
    totals = []
    for lib, q in QUERIES:
        total = None
        for page in range(1, PAGES + 1):
            data = search(q, page)
            (raw / f"{lib}__{q.replace(' ', '_').replace('/', '_').replace(':', '-')}__p{page}.json").write_text(
                json.dumps(data), encoding="utf-8")
            total = data.get("total_count", 0)
            items = data.get("items", [])
            for it in items:
                repo = it["repository"]
                key = (repo["full_name"], it["path"])
                r = rows.setdefault(key, {"repo": repo["full_name"], "path": it["path"], "fork": repo.get("fork", False),
                                          "html_url": it["html_url"], "libraries": set(), "queries": set()})
                r["libraries"].add(lib)
                r["queries"].add(q)
            time.sleep(7)  # stay under the code-search rate limit
            if len(items) < 100 or page * 100 >= total:
                break
        totals.append((lib, q, total))
        print(f"{lib:18} {q!r}: total {total}", flush=True)
    with (HERE / "candidates.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["repo", "path", "fork", "html_url", "libraries", "queries"])
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: (r["repo"], r["path"])):
            w.writerow(dict(r, libraries="; ".join(sorted(r["libraries"])), queries="; ".join(sorted(r["queries"]))))
    with (HERE / "query-totals.csv").open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([("library", "query", "total_count"), *totals])
    print(f"{len(rows)} (repository, file) pairs from {len({r['repo'] for r in rows.values()})} repositories")


if __name__ == "__main__":
    main()
