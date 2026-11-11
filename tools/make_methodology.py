"""Draws methodology.png (Fig. 2 of the paper): the order in which data, labels, training and evaluation happen.
Eight numbered steps, read left to right on the top row, then right to left on the bottom row.
Colours match make_architecture.py: ink #16202B, amber #B26A00 (shared code / model artefact), teal #16697A (reference labels).
Run:  python tools/make_methodology.py [out_dir]
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK, AMBER, TEAL, PAPER = "#16202B", "#B26A00", "#16697A", "#FFFFFF"
out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

fig, ax = plt.subplots(figsize=(7.3, 3.3))
ax.set_xlim(0, 100); ax.set_ylim(0, 46); ax.axis("off")

BW, BH = 21.0, 15.5
XS = [1.0, 26.0, 51.0, 76.0]          # gaps of 4 units between boxes
Y_TOP, Y_BOT = 28.5, 8.0
boxes = {}


def box(n, col, row_y, title, body, edge=INK, ls="-", lw=1.1):
    x = XS[col]
    ax.add_patch(FancyBboxPatch((x, row_y), BW, BH, boxstyle="round,pad=0,rounding_size=0.9",
                                fc=PAPER, ec=edge, lw=lw, ls=ls))
    ax.text(x + 1.4, row_y + BH - 2.2, str(n), fontsize=7.2, fontweight="bold", color=edge, va="center")
    ax.text(x + 4.4, row_y + BH - 2.2, title, fontsize=6.4, fontweight="bold", color=INK, va="center")
    ax.text(x + 1.6, row_y + BH - 5.0, body, fontsize=5.6, color=INK, va="top", linespacing=1.35)
    boxes[n] = (x, row_y)


def arrow(p, q, color=INK):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=8, lw=1.1, color=color))


# top row: left to right
box(1, 0, Y_TOP, "Corpus", "APIs.guru directory\n(APIstic not used);\nsnapshot date and URL stored")
box(2, 1, Y_TOP, "Clean and group", "drop exact duplicates\n(spec hash); tag every\nendpoint with its provider")
box(3, 2, Y_TOP, "S0 Normalise", "one record per endpoint;\nparse-failure rate\nreported", edge=AMBER, lw=1.6)
box(4, 3, Y_TOP, "S1 Scan, S2a", "Spectral + OWASP findings;\nthen 66 features per\nendpoint (groups A to F)", edge=AMBER, lw=1.6)
# bottom row: right to left
box(5, 3, Y_BOT, "Attach labels", "L1 scanner labels: train only\nL2 LLM labels (304):\ntrain and test\nL3 truth: test only", edge=TEAL, ls="--", lw=1.4)
box(6, 2, Y_BOT, "Split and tune", "5-fold, folds grouped by\nprovider; inner grouped CV;\nscale_pos_weight", )
box(7, 1, Y_BOT, "Fit XGBoost", "5 seeds, versions pinned;\nwrites model.json with seed,\nversions, corpus date", edge=AMBER, lw=1.6)
box(8, 0, Y_BOT, "Evaluate E1 to E9", "scored against L2 and L3\nreference labels only;\nE2 removes one OWASP\ncategory", lw=1.8)

mid = Y_TOP + BH / 2
for a, b in [(0, 1), (1, 2), (2, 3)]:
    arrow((XS[a] + BW, mid), (XS[b], mid), AMBER if b >= 2 else INK)
arrow((XS[3] + BW / 2, Y_TOP), (XS[3] + BW / 2, Y_BOT + BH))
midb = Y_BOT + BH / 2
for a, b in [(3, 2), (2, 1), (1, 0)]:
    arrow((XS[a], midb), (XS[b] + BW, midb), AMBER if a <= 2 else INK)

ax.text(50, 3.4, "Rule: every score is measured against reference labels (L2 by language models, L3 documented flaws), never against the scanner labels (L1) the model was trained on.",
        fontsize=6.0, color=TEAL, ha="center", va="center", style="italic")
ax.plot([4, 96], [6.0, 6.0], color=TEAL, lw=0.6, ls="--")

fig.savefig(out / "methodology.png", dpi=300, bbox_inches="tight", facecolor="white")
fig.savefig(out / "methodology.pdf", bbox_inches="tight", facecolor="white")
print("wrote", out / "methodology.png")
