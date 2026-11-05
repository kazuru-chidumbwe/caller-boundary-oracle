#!/usr/bin/env python3
"""Figure 7: consequence demo (T13) from the run records in analysis/out/t13.

Usage: python analysis/figure_t13.py OUT_BASENAME   (writes OUT_BASENAME.png at 300 dpi and .pdf)
Three panels, each one SampleReader run: the Active Authentication exchange as recorded in the
run's APDU trace, what doAA returned, and what the application showed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent / "out" / "t13"

PANELS = [
    ("R1", "Chip refuses AA\ncommon integration pattern"),
    ("R3", "Chip refuses AA\nresponse checked by the app"),
    ("R2", "Chip signs the challenge\ncommon integration pattern"),
]


def aa_lines(run: dict) -> tuple[str, str]:
    ia = next(t for t in run["trace"] if t["label"] == "INS 88")
    rsp = ia["rapdu"]
    sw = rsp[-4:]
    if rsp.startswith("9902"):
        chip = f"protected status {rsp[4:8]}\n(DO'99' + MAC), no data"
    else:
        chip = f"{run['aa_response_length']}-byte signature\nstatus {sw}"
    return "INTERNAL AUTHENTICATE\n8-byte challenge, protected", chip


def box(ax, x, y, w, h, text, fc, ec="#333333", bold=False, size=7):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008,rounding_size=0.012",
                                fc=fc, ec=ec, lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
            fontweight="bold" if bold else "normal", linespacing=1.3)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", lw=0.8, color="#333333"))


def main() -> None:
    out = Path(sys.argv[1])
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    w, gap = 0.30, 0.035
    for i, (rid, title) in enumerate(PANELS):
        run = json.loads((HERE / f"{rid}.json").read_text())
        x = 0.01 + i * (w + gap)
        ax.text(x + w / 2, 0.97, title, ha="center", va="top", fontsize=7.8, fontweight="bold", linespacing=1.3)
        cmd, chip = aa_lines(run)
        box(ax, x, 0.70, w, 0.11, "Reader: " + cmd, "#ffffff")
        arrow(ax, x + w / 2, 0.70, x + w / 2, 0.665)
        box(ax, x, 0.55, w, 0.11, "Chip: " + chip, "#f2f2f2")
        arrow(ax, x + w / 2, 0.55, x + w / 2, 0.515)
        n = run["aa_response_length"]
        box(ax, x, 0.40, w, 0.11, f"doAA returns normally\nAAResult response: {n} bytes", "#ffffff")
        arrow(ax, x + w / 2, 0.40, x + w / 2, 0.365)
        check = "app checks response is non-empty" if run["mode"] == "defensive" else "app trusts doAA (no check)"
        box(ax, x, 0.25, w, 0.11, check, "#ffffff")
        arrow(ax, x + w / 2, 0.25, x + w / 2, 0.215)
        verdict = "authentic = true" if run["authentic"] else "authentic = false"
        wrong = run["authentic"] and run["aa_refused_by_chip"]
        fc = "#d9d9d9" if wrong else "#ffffff"
        doc_no, _, name = (run["document_shown"] or "").partition(" ")
        box(ax, x, 0.05, w, 0.16, f"App shows {doc_no}\n{name}\n{verdict}", fc, ec="#000000",
            bold=True, size=7)
    ax.text(0.5, -0.02, "Grey: a document whose chip refused Active Authentication is shown as authentic.",
            ha="center", va="bottom", fontsize=6.5, style="italic")
    fig.savefig(out.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")


if __name__ == "__main__":
    main()
