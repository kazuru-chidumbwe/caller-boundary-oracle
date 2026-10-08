#!/usr/bin/env python3
"""Figure 1: the method pipeline, from profile to verified outcome (greyscale, labels only, no colour coding).

Usage: python analysis/figure_pipeline.py OUT_BASENAME   (writes OUT_BASENAME.png at 300 dpi and .pdf)
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

INK, FILL, PALE = "#000000", "#e6e6e6", "#f5f5f5"


def box(ax, x, y, w, h, title, lines, fill=FILL):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                linewidth=1.0, edgecolor=INK, facecolor=fill))
    ax.text(x + w / 2, y + h - 0.035, title, ha="center", va="top", fontsize=7.8, fontweight="bold")
    ax.text(x + w / 2, y + h - 0.085, "\n".join(lines), ha="center", va="top", fontsize=7, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, label=None, both=False, dy=0.012):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="<|-|>" if both else "-|>",
                                 mutation_scale=9, linewidth=0.9, color=INK))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, label, ha="center", va="bottom", fontsize=6.5, style="italic")


def main() -> int:
    out = sys.argv[1]
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.set_xlim(-0.02, 1.86)
    ax.set_ylim(0, 0.76)
    ax.axis("off")
    W, G = 0.28, 0.10
    X = [i * (W + G) for i in range(5)]
    box(ax, X[0], 0.40, W, 0.30, "Profile", ["one fault and", "its delivery point:", "step, status word,", "channel fault or case"])
    box(ax, X[1], 0.40, W, 0.30, "Fault peer", ["harness chip,", "independent chip", "(vsmartcard, OpenPACE),", "software authenticator"])
    box(ax, X[2], 0.40, W, 0.30, "Driver and library", ["the library called as", "an application calls it,", "in one caller arm", "(default, opt-in, guard)"])
    box(ax, X[3], 0.40, W, 0.30, "Observations", ["fired: from the peer", "failed, succeeded,", "returned_error,", "status_signal: library"])
    box(ax, X[4], 0.40, W, 0.30, "Oracle (frozen)", ["surfaced, status-only,", "silent, not applicable", "or invalid; one decision", "procedure everywhere"], fill=PALE)
    for i in range(4):
        if i == 1:
            arrow(ax, X[1] + W, 0.55, X[2], 0.55, both=True)
            ax.text(X[1] + W + G / 2, 0.715, "APDUs or responses", ha="center", va="bottom", fontsize=6, style="italic")
        else:
            arrow(ax, X[i] + W, 0.55, X[i + 1], 0.55)
    ax.add_patch(FancyArrowPatch((X[1] + W / 2, 0.40), (X[3] + W / 2, 0.40), connectionstyle="arc3,rad=0.35",
                                 arrowstyle="-|>", mutation_scale=9, linewidth=0.9, color=INK, linestyle=(0, (3, 2))))
    ax.text((X[1] + X[3] + W) / 2, 0.24, "delivery report: was the fault delivered unchanged?", ha="center",
            fontsize=6.5, style="italic")
    box(ax, X[4], 0.02, W, 0.19, "Run artifact", ["outcome, trace,", "observations,", "provenance"])
    box(ax, X[3], 0.02, W, 0.19, "Verification", ["against the expectation", "fixed before the run"], fill=PALE)
    arrow(ax, X[4] + W / 2, 0.40, X[4] + W / 2, 0.21)
    arrow(ax, X[4], 0.115, X[3] + W, 0.115)
    fig.tight_layout(pad=0.2)
    fig.savefig(out + ".png", dpi=300)
    fig.savefig(out + ".pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
