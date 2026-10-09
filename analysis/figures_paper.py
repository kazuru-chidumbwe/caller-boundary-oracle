#!/usr/bin/env python3
"""Figures for the paper beyond Figure 1 (pipeline) and the behaviour map (figure_behaviour.py).

  fig-code-studies.png   M1 sites per library and step (stacked bars); M2 screening decisions (donut)
                         and eligible call sites per library
  fig-mutation.png       RQ1: (mutant, arm) pairs whose outcome changed, detected per oracle, overall
                         and by kind of change (the unit of Table 8)
  fig-outcome-mix.png    RQ2: share of outcomes per arm over its fault cells (100% stacked bars),
                         passauf under both readings
  fig-evolution.png      RQ3: gmrtd release strip, outcome per mechanism and arm for every release

Inputs are the committed outputs of the analysis scripts; nothing is re-run here.
Usage: python analysis/figures_paper.py [--out DIR]   (default analysis/out)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Outcome colours: ordered from worst (silent) to best (surfaced); readable in greyscale.
COL = {"silent": "#b2182b", "status_only": "#f4a582", "surfaced": "#2166ac",
       "not_applicable": "#d9d9d9", "abort": "#762a83", "no_return": "#40004b"}
LABEL = {"silent": "silent", "status_only": "status-only", "surfaced": "surfaced",
         "not_applicable": "not applicable", "abort": "abort (panic)", "no_return": "no return"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.dpi": 300, "savefig.bbox": "tight"})


def code_studies(out: Path) -> None:
    sites = list(csv.DictReader((ROOT / "mining/m1-sites.csv").open(encoding="utf-8")))
    libs = ["gmrtd", "jmrtd", "emrtd-dotnet", "dmrtd", "nfcpassportreader", "passauf"]
    names = {"gmrtd": "gmrtd", "jmrtd": "JMRTD", "emrtd-dotnet": "emrtd-dotnet", "dmrtd": "dmrtd",
             "nfcpassportreader": "NFCPassportReader", "passauf": "passauf"}
    steps = ["PACE", "BAC", "CA", "AA", "SM"]
    other = "other"
    cnt = Counter((s["library"].lower(), s["step_hint"] if s["step_hint"] in steps else other) for s in sites)
    libs = [l for l in libs if any(k[0] == l for k in cnt)]
    summ = json.loads((ROOT / "mining/m2/screen/SUMMARY.json").read_text(encoding="utf-8"))

    fig = plt.figure(figsize=(7.2, 2.6))
    ax = fig.add_axes([0.08, 0.15, 0.42, 0.75])
    left = [0] * len(libs)
    pal = ["#2166ac", "#67a9cf", "#d1e5f0", "#fddbc7", "#ef8a62", "#bdbdbd"]
    for step, c in zip(steps + [other], pal):
        vals = [cnt[(l, step)] for l in libs]
        if not any(vals):
            continue
        ax.barh(range(len(libs)), vals, left=left, color=c, edgecolor="white", linewidth=0.5, label=step)
        left = [a + b for a, b in zip(left, vals)]
    for i, t in enumerate(left):
        ax.text(t + 3, i, str(t), va="center", fontsize=7)
    ax.set_yticks(range(len(libs)), [names[l] for l in libs])
    ax.invert_yaxis()
    ax.set_xlabel("failure-handling sites (M1)")
    ax.set_title(f"(a) M1: {len(sites)} sites by step", loc="left", fontsize=8)
    ax.legend(ncol=5, fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), handlelength=1)

    dec = summ["by_decision"]
    parts = [("included", dec.get("included", 0), "#2166ac"),
             ("calls none of the APIs", dec.get("not_included", 0), "#d9d9d9"),
             ("BAC only (E4)", dec.get("E4", 0), "#f4a582"),
             ("tutorial (E3)", dec.get("E3", 0), "#fddbc7"),
             ("library copy (E1)", dec.get("E1", 0), "#b2182b")]
    ax2 = fig.add_axes([0.49, 0.1, 0.22, 0.8])
    total = sum(p[1] for p in parts)
    ax2.pie([p[1] for p in parts], colors=[p[2] for p in parts], startangle=90, counterclock=False,
            wedgeprops={"width": 0.38, "edgecolor": "white"})
    ax2.text(0, 0, f"{total}\nrepositories", ha="center", va="center", fontsize=7)
    ax2.legend([Patch(color=p[2]) for p in parts], [f"{p[0]} ({p[1]})" for p in parts],
               fontsize=6.5, frameon=False, loc="upper left", bbox_to_anchor=(0.95, 1.0))
    ax2.set_title("(b) M2 screening", loc="left", fontsize=8)

    ax3 = fig.add_axes([0.88, 0.12, 0.11, 0.36])
    by = summ["call_sites_by_library"]
    order = sorted(by, key=lambda k: -by[k])
    ax3.barh(range(len(order)), [by[k] for k in order], color="#2166ac")
    ax3.set_yticks(range(len(order)), [names.get(k, k).replace("NFCPassportReader", "NFCPassport-\nReader") for k in order], fontsize=6.5)
    ax3.invert_yaxis()
    for i, k in enumerate(order):
        ax3.text(by[k] + 3, i, str(by[k]), va="center", fontsize=6.5)
    ax3.set_xlabel(f"call sites ({summ['call_sites']})", fontsize=6.5)
    fig.savefig(out / "fig-code-studies.png")
    plt.close(fig)


def _md_table(text: str, header_start: str) -> list[list[str]]:
    rows, on = [], False
    for line in text.splitlines():
        if line.startswith(header_start):
            on = True
            continue
        if on and line.startswith("| ---"):
            continue
        if on and line.startswith("|"):
            rows.append([c.strip() for c in line.strip("|").split("|")])
        elif on:
            break
    return rows


def mutation(out: Path) -> None:
    """RQ1 on the paper's unit, (mutant, arm) pairs whose fault was delivered and whose outcome changed
    (mutation/out/PER-ARM.md, from per_arm.py): (a) pairs each oracle detects, (b) by kind of change."""
    md = (ROOT / "mutation/out/PER-ARM.md").read_text(encoding="utf-8")
    tot = _md_table(md, "| oracle | pairs detected")
    kinds = _md_table(md, "| reference outcome | mutant outcome")
    names = ["caller-boundary oracle", "any error", "output differential", "conformance verdict"]
    cols = ["#2166ac", "#67a9cf", "#f4a582", "#b2182b"]
    fig = plt.figure(figsize=(7.2, 2.7))
    ax = fig.add_axes([0.17, 0.2, 0.25, 0.68])
    det = [int(r[1]) for r in tot]
    n = int(tot[0][2])
    ax.barh(range(4), [n] * 4, color="#f0f0f0", edgecolor="#bdbdbd", linewidth=0.5)
    ax.barh(range(4), det, color=cols)
    for i, v in enumerate(det):
        ax.text(v + 1, i, f"{v}/{n}", va="center", fontsize=6.5)
    ax.set_yticks(range(4), names, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, n * 1.25)
    ax.set_xlabel("pairs detected")
    ax.set_title(f"(a) all {n} changed pairs", loc="left", fontsize=8)
    lab = {"status_only": "status-only"}
    ax2 = fig.add_axes([0.5, 0.2, 0.49, 0.68])
    w = 0.2
    for i, r in enumerate(kinds):
        pairs = int(r[3])
        vals = [pairs, int(r[4]), int(r[5]), int(r[6])]
        for j, v in enumerate(vals):
            ax2.bar(i + (j - 1.5) * w, v, w, color=cols[j])
            if v == 0:
                ax2.text(i + (j - 1.5) * w, 0.6, "0", ha="center", fontsize=6, color=cols[j])
    ax2.set_xticks(range(len(kinds)), [f"{lab.get(r[0], r[0])}\n\u2192 {lab.get(r[1], r[1])}" for r in kinds], fontsize=6.5)
    ax2.set_ylabel("pairs detected")
    ax2.set_title("(b) by kind of change in what the caller is told", loc="left", fontsize=8)
    ax2.legend([Patch(color=c) for c in cols], names, fontsize=6.5, frameon=False, loc="upper right")
    fig.savefig(out / "fig-mutation.png")
    plt.close(fig)


def outcome_mix(out: Path) -> None:
    beh = list(csv.DictReader((ROOT / "analysis/out/behaviour.csv").open(encoding="utf-8")))
    arms: dict[str, Counter] = defaultdict(Counter)
    for r in beh:
        if r["mechanism"] == "CONTROL":
            continue
        for o, n in re.findall(r"(silent|status_only|surfaced|not_applicable) (\d+)", r["outcomes"]):
            arms[r["arm"]][o] += 1   # cells, not runs: each row is one fault point on one chip
    res = [json.loads(l) for l in (ROOT / "passauf/heldout/run-f1553f2/results.jsonl").open(encoding="utf-8")]
    pre, strict = Counter(), Counter()
    for r in res:   # fault cells with a delivered failure run once each (n = 1); controls and success runs are n/a
        if r["outcome"] == "not_applicable":
            continue
        pre[r["outcome"]] += 1
        strict["abort" if r.get("panic") else "no_return" if r.get("hang") else r["outcome"]] += 1
    order = sorted(arms, key=lambda a: (a.split()[0].lower(), a))
    data = [(a, arms[a]) for a in order] + [("passauf (pre-registered)", pre), ("passauf (strict)", strict)]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    cats = ["silent", "no_return", "abort", "status_only", "surfaced", "not_applicable"]
    for i, (name, c) in enumerate(data):
        tot = sum(c.values()) or 1
        left = 0.0
        for k in cats:
            v = 100 * c[k] / tot
            if v:
                ax.barh(i, v, left=left, color=COL[k], edgecolor="white", linewidth=0.4)
                if v >= 8:
                    ax.text(left + v / 2, i, f"{c[k]}", ha="center", va="center", fontsize=6,
                            color="white" if k in ("silent", "surfaced", "abort", "no_return") else "black")
                left += v
    ax.set_yticks(range(len(data)), [d[0] for d in data], fontsize=7)
    ax.invert_yaxis()
    ax.axhline(len(order) - 0.5, color="black", linewidth=0.6, linestyle=":")
    ax.set_xlabel("fault cells (%); numbers are cell counts")
    ax.set_xlim(0, 100)
    ax.legend([Patch(color=COL[k]) for k in cats], [LABEL[k] for k in cats], ncol=6, fontsize=6.5,
              frameon=False, loc="upper center", bbox_to_anchor=(0.45, 1.08))
    fig.savefig(out / "fig-outcome-mix.png")
    plt.close(fig)


def evolution(out: Path) -> None:
    d = json.loads((ROOT / "analysis/out/version-sweep.json").read_text(encoding="utf-8"))
    rels = list(d)
    cols = [("PACE", "default"), ("PACE", "allow-fallback"), ("PACE", "guard"),
            ("CA", "default"), ("CA", "guard"), ("AA", "default"), ("AA", "guard")]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for i, rel in enumerate(rels):
        runs = d[rel]["runs"]
        for j, (mech, arm) in enumerate(cols):
            if not runs:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, facecolor="white", edgecolor="#bdbdbd", hatch="////", linewidth=0.3))
                continue
            c = Counter(v["outcome"] for k, v in runs.items() if k.split("|")[1:] == [mech, arm])
            if not c:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, facecolor="white", edgecolor="#d9d9d9", linewidth=0.3))
                ax.text(j + 0.5, i + 0.5, "n/a", ha="center", va="center", fontsize=5, color="#969696")
                continue
            tot, x = sum(c.values()), j
            for k in ("silent", "status_only", "surfaced", "not_applicable"):
                if c[k]:
                    wdt = c[k] / tot
                    ax.add_patch(plt.Rectangle((x, i), wdt, 1, facecolor=COL[k], edgecolor="white", linewidth=0.3))
                    x += wdt
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(rels), 0)
    ax.set_xticks([j + 0.5 for j in range(len(cols))],
                  [f"{m}\n{a.replace('allow-fallback', 'opt-in')}" for m, a in cols], fontsize=7)
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.5 for i in range(len(rels))], rels, fontsize=6.5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    handles = [Patch(color=COL[k]) for k in ("silent", "status_only", "surfaced", "not_applicable")]
    handles.append(Patch(facecolor="white", edgecolor="#bdbdbd", hatch="////"))
    ax.legend(handles, ["silent", "status-only", "surfaced", "not applicable", "does not build with the driver"],
              ncol=5, fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.01))
    fig.savefig(out / "fig-evolution.png")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "analysis" / "out")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for f in (code_studies, mutation, outcome_mix, evolution):
        f(a.out)
        print("wrote", f.__name__)


if __name__ == "__main__":
    main()
