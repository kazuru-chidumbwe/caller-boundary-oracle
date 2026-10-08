#!/usr/bin/env python3
"""Figure: behaviour class per arm, step and chip, drawn from analysis/out/behaviour.csv.

Darker means less reaches the caller: surfaced (light), status-only (middle), silent (dark).
A cell whose outcome depends on the failure kind is split in proportion to the failure kinds,
and every cell carries a text label, so the figure reads in greyscale.

Usage: python analysis/figure_behaviour.py [--csv analysis/out/behaviour.csv] [--out analysis/out/figure-behaviour.png]
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
# One-hue ordinal ramp (light to dark), checked for monotone lightness and surface contrast.
FILL = {"surfaced": "#86b6ef", "status_only": "#2a78d6", "silent": "#104281"}
INK = {"surfaced": "#1a1a19", "status_only": "#ffffff", "silent": "#ffffff"}
SHORT = {"surfaced": "Su", "status_only": "SO", "silent": "Si"}
ABSENT = "#ebeae6"
ORDER = ("surfaced", "status_only", "silent")

ARMS = [
    "gmrtd 0.45.0 default", "gmrtd 0.45.0 + guard",
    "gmrtd 1.1.3 default", "gmrtd 1.1.3 opt-in fallback", "gmrtd 1.1.3 + guard",
    "gmrtd 1.3.2 default", "gmrtd 1.3.2 opt-in fallback", "gmrtd 1.3.2 + guard",
    "JMRTD 0.8.9 propagate", "JMRTD 0.8.9 catch-and-continue", "JMRTD 0.5.0 Passport",
    "emrtd-dotnet", "dmrtd", "NFCPassportReader",
]
COLUMNS = [
    ("PACE", "harness", "PACE\nharness chip"),
    ("PACE", "independent", "PACE\nindependent chip"),
    ("CA", "harness", "CA\nharness chip"),
    ("AA", "harness", "AA\nharness chip"),
    ("AA", "independent", "AA\nindependent chip"),
]
# Steps a library does not implement (as opposed to arms not run on a step).
NOT_IMPLEMENTED = {("emrtd-dotnet", "CA"), ("emrtd-dotnet", "AA"), ("dmrtd", "CA")}


def load(path: Path) -> dict[tuple[str, str, str], Counter]:
    """Failure kinds per outcome for each (arm, mechanism, chip); controls and n/a left out."""
    cells: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["fault point"] == "control":
                continue
            for part in row["outcomes"].split(","):
                outcome, n = part.strip().rsplit(" ", 1)
                if outcome in FILL:
                    cells[(row["arm"], row["mechanism"], row["chip"])][outcome] += int(n)
    return cells


def draw(cells: dict[tuple[str, str, str], Counter], out: Path) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    w, h = 1.0, 1.0
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    for r, arm in enumerate(ARMS):
        y = len(ARMS) - 1 - r
        for c, (mech, chip, _) in enumerate(COLUMNS):
            counts = cells.get((arm, mech, chip))
            x = c * w
            if not counts:
                library = arm.split(" ")[0].replace("JMRTD", "jmrtd")
                absent = (library, mech) in NOT_IMPLEMENTED
                ax.add_patch(Rectangle((x + 0.02, y + 0.04), w - 0.04, h - 0.08, color=ABSENT, lw=0))
                ax.text(x + w / 2, y + h / 2, "not implemented" if absent else "not run",
                        ha="center", va="center", color="#6b6a65", fontsize=6.5)
                continue
            total = sum(counts.values())
            left = x + 0.02
            span = w - 0.04
            present = [o for o in ORDER if counts[o]]
            for i, o in enumerate(present):
                width = span * counts[o] / total
                gap = 0.02 if i < len(present) - 1 else 0.0  # 2 px-style surface gap between segments
                ax.add_patch(Rectangle((left, y + 0.04), width - gap, h - 0.08, color=FILL[o], lw=0))
                label = SHORT[o] if len(present) == 1 else f"{SHORT[o]} {counts[o]}"
                ax.text(left + (width - gap) / 2, y + h / 2, label, ha="center", va="center",
                        color=INK[o], fontsize=7.5)
                left += width
    ax.set_xlim(0, len(COLUMNS) * w)
    ax.set_ylim(0, len(ARMS) * h)
    ax.set_xticks([c * w + w / 2 for c in range(len(COLUMNS))], [label for *_, label in COLUMNS])
    ax.xaxis.tick_top()
    ax.set_yticks([len(ARMS) - 1 - r + h / 2 for r in range(len(ARMS))], ARMS)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    handles = [Patch(color=FILL[o], label=n) for o, n in
               (("surfaced", "Su  surfaced (error returned)"), ("status_only", "SO  status-only (field only)"),
                ("silent", "Si  silent (nothing visible)"))]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3, frameon=False,
              handlelength=1.2, fontsize=7.5)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=600, facecolor="white", bbox_inches="tight", pad_inches=0.05)
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=HERE / "out" / "behaviour.csv")
    ap.add_argument("--out", type=Path, default=HERE / "out" / "figure-behaviour.png")
    a = ap.parse_args()
    draw(load(a.csv), a.out)


if __name__ == "__main__":
    main()
