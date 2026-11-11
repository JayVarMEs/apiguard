#!/usr/bin/env python3
"""Generate architecture.svg for APIGUARD.

Hand-written SVG using presentation attributes only (no CSS), so the figure
survives import into Word for the dissertation.
"""

INK = "#16202B"
AMBER = "#B26A00"
TEAL = "#16697A"
MUTED = "#5A6672"
BAND = "#F4F6F8"
BAND2 = "#FAF6F0"
BAND3 = "#F2F8F9"
WHITE = "#FFFFFF"
FONT = "Segoe UI,Calibri,Helvetica Neue,Arial,sans-serif"

W, H = 1380, 880
parts = []


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=14, fill=INK, weight="normal", anchor="middle", style="normal"):
    parts.append(
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}" font-style="{style}" text-anchor="{anchor}">{esc(s)}</text>'
    )


def band(x, y, w, h, fill, label, label_colour):
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
        f'stroke="none"/>'
    )
    parts.append(
        f'<text x="{x + 16}" y="{y + 26}" font-family="{FONT}" font-size="13" '
        f'fill="{label_colour}" font-weight="bold" letter-spacing="1.5" '
        f'text-anchor="start">{esc(label)}</text>'
    )


def box(x, y, w, h, lines, stroke=INK, fill=WHITE, tag=None, dash=None,
        title_size=14, body_size=11.5):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.8"{d}/>'
    )
    if tag:
        parts.append(
            f'<text x="{x + 10}" y="{y + 18}" font-family="{FONT}" font-size="11" '
            f'fill="{stroke}" font-weight="bold" text-anchor="start">{esc(tag)}</text>'
        )
    cx = x + w / 2
    n = len(lines)
    start = y + h / 2 - (n - 1) * 9 + (6 if tag else 0)
    for i, ln in enumerate(lines):
        size = title_size if i == 0 else body_size
        colour = INK if i == 0 else MUTED
        weight = "600" if i == 0 else "normal"
        text(cx, start + i * 18, ln, size=size, fill=colour, weight=weight)


def arrow(x1, y1, x2, y2, colour=INK, dash=None, marker="arrow", width=1.8):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
        f'stroke-width="{width}"{d} marker-end="url(#{marker})"/>'
    )


def path(d, colour=INK, dash=None, marker="arrow", width=1.8):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}"{da} '
        f'marker-end="url(#{marker})"/>'
    )


# ---------------------------------------------------------------- defs
defs = []
for name, colour in (("arrow", INK), ("arrowAmber", AMBER), ("arrowTeal", TEAL)):
    defs.append(
        f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{colour}"/></marker>'
    )

parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{WHITE}"/>')

# ---------------------------------------------------------------- title
text(W / 2, 42, "APIGUARD — Continuous API Security Assessment in DevSecOps Pipelines",
     size=20, weight="600")
text(W / 2, 66, "Rule scanning stays authoritative; the model ranks every endpoint and "
                "explains why", size=13, fill=MUTED, style="italic")

# ---------------------------------------------------------------- runtime lane
band(30, 92, W - 60, 218, BAND, "RUNTIME  ·  in the pipeline", MUTED)

box(50, 160, 150, 92, ["OpenAPI spec", "OpenAPI 3.x /", "Swagger 2.0"])
box(230, 160, 165, 92, ["Normaliser", "parse to one", "internal form"], tag="S0")
box(425, 160, 185, 92, ["Rule scanner", "Spectral + OWASP", "ruleset (2023)"], tag="S1")

# S2 container
box(640, 138, 350, 136, [], tag="S2")
text(815, 158, "AI verifier", size=14, weight="600")
box(650, 176, 100, 78, ["Feature", "builder"], tag="S2a", title_size=12.5, body_size=11)
box(770, 176, 100, 78, ["XGBoost"], tag="S2b", title_size=12.5, body_size=11)
box(890, 176, 90, 78, ["SHAP"], tag="S2c", title_size=12.5, body_size=11)

box(1020, 160, 165, 92, ["Risk gate", "score vs threshold τ"], tag="S3")

text(1290, 188, "pass → exit 0", size=12.5, fill=MUTED)
text(1290, 214, "fail → exit 1", size=12.5, fill=MUTED)

arrow(200, 206, 226, 206)
arrow(395, 206, 421, 206)
arrow(610, 206, 636, 206)
arrow(750, 215, 766, 215)
arrow(870, 215, 886, 215)
arrow(990, 206, 1016, 206)
arrow(1185, 195, 1225, 195, colour=MUTED, width=1.4)
arrow(1185, 221, 1225, 221, colour=MUTED, width=1.4)

# ---------------------------------------------------------------- offline lane
band(30, 350, W - 60, 210, BAND2, "OFFLINE  ·  training", AMBER)

box(50, 414, 165, 92, ["Corpus", "APIs.guru,", "APIstic"], tag="T1")
box(245, 414, 175, 92, ["Labels", "scanner + LLM labels", "+ vulnerable apps"], tag="T2")
box(450, 414, 210, 92, ["Shared core", "same S0 + S2a code", "as runtime"], tag="T3",
    stroke=AMBER)
box(690, 414, 165, 92, ["Trainer", "grouped splits,", "fixed seeds"], tag="T4")
box(885, 414, 150, 92, ["model.json", "trained artefact"], stroke=AMBER)

arrow(215, 460, 241, 460)
arrow(420, 460, 446, 460)
arrow(660, 460, 686, 460)
arrow(855, 460, 881, 460)
text(690, 536, "retraining is run deliberately, never automatically", size=11.5, fill=AMBER)

# model.json -> S2b (loaded at startup)
path("M 960 414 L 960 330 L 820 330 L 820 258", colour=AMBER, marker="arrowAmber")
text(880, 320, "loaded at startup", size=12, fill=AMBER)

# shared code link T3 -> S0 / S2a
path("M 500 414 L 500 336 L 312 336 L 312 256", colour=AMBER, dash="6 5",
     marker="arrowAmber", width=1.6)
text(456, 326, "identical code path", size=11.5, fill=AMBER)

# ---------------------------------------------------------------- feedback lane
band(30, 600, W - 60, 200, BAND3, "FEEDBACK  ·  human review", TEAL)

box(880, 660, 220, 92, ["Developer / analyst", "reviews the verdict"], stroke=TEAL)
box(520, 660, 250, 92, ["Feedback queue", "feedback.jsonl"], stroke=TEAL)

path("M 1102 252 L 1102 656", colour=TEAL, dash="7 5", marker="arrowTeal")
path("M 876 706 L 774 706", colour=TEAL, dash="7 5", marker="arrowTeal")
path("M 520 706 L 332 706 L 332 510", colour=TEAL, dash="7 5", marker="arrowTeal")

text(1140, 470, "no arrow from the gate", size=12, fill=TEAL, anchor="start")
text(1140, 490, "back into the model —", size=12, fill=TEAL, anchor="start")
text(1140, 510, "that would train it on", size=12, fill=TEAL, anchor="start")
text(1140, 530, "its own output", size=12, fill=TEAL, anchor="start")

# ---------------------------------------------------------------- legend
parts.append(f'<line x1="50" y1="836" x2="86" y2="836" stroke="{AMBER}" stroke-width="2.4"/>')
text(96, 841, "shared code and model artefact (dashed = identical code path)", size=12, fill=MUTED, anchor="start")
parts.append(f'<line x1="514" y1="836" x2="550" y2="836" stroke="{TEAL}" '
             f'stroke-width="2.4" stroke-dasharray="7 5"/>')
text(560, 841, "human-in-the-loop path", size=12, fill=MUTED, anchor="start")
text(W - 50, 841, "Unit of analysis: one endpoint (path + method)", size=12,
     fill=MUTED, anchor="end")

svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}">\n<defs>\n' + "\n".join(defs) + "\n</defs>\n"
    + "\n".join(parts) + "\n</svg>\n"
)

with open("architecture.svg", "w", encoding="utf-8") as f:
    f.write(svg)

print("written", len(svg), "bytes")
