#!/usr/bin/env python3
"""Build architecture_editable.pptx for APIGUARD.

Every element is a native PowerPoint object: autoshapes, connectors and text
boxes.  Nothing is a picture, so the whole figure can be dragged, retyped and
recoloured inside PowerPoint.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
import copy

INK   = RGBColor(0x16, 0x20, 0x2B)
AMBER = RGBColor(0xB2, 0x6A, 0x00)
TEAL  = RGBColor(0x16, 0x69, 0x7A)
MUTED = RGBColor(0x5A, 0x66, 0x72)
BAND  = RGBColor(0xF4, 0xF6, 0xF8)
BAND2 = RGBColor(0xFA, 0xF6, 0xF0)
BAND3 = RGBColor(0xF2, 0xF8, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT  = "Segoe UI"

# SVG canvas was 1380 x 880 px -> 1 px == 0.01 in
SX = 0.01

prs = Presentation()
prs.slide_width  = Inches(13.80)
prs.slide_height = Inches(8.80)
slide = prs.slides.add_slide(prs.slide_layouts[6])   # blank
shapes = slide.shapes


def E(px):
    return Inches(px * SX)


def pt(px):
    return Pt(round(px * 0.78, 1))


def set_arrow(conn, colour, dashed=False, width=1.6):
    ln = conn.line
    ln.color.rgb = colour
    ln.width = Pt(width)
    lnEl = ln._get_or_add_ln()
    for tag in ("a:tailEnd",):
        el = lnEl.find(qn(tag))
        if el is not None:
            lnEl.remove(el)
    tail = lnEl.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    lnEl.append(tail)
    if dashed:
        dash = lnEl.makeelement(qn("a:prstDash"), {"val": "dash"})
        # prstDash must sit before tailEnd in the schema order
        lnEl.insert(list(lnEl).index(tail), dash)


def textbox(x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """runs = list of (text, size_px, colour, bold, italic)"""
    tb = shapes.add_textbox(E(x), E(y), E(w), E(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    for i, (txt, size, colour, bold, italic) in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = txt
        f = r.font
        f.name = FONT
        f.size = pt(size)
        f.bold = bold
        f.italic = italic
        f.color.rgb = colour
    return tb


def band(x, y, w, h, fill, label, label_colour):
    s = shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, E(x), E(y), E(w), E(h))
    s.adjustments[0] = 0.05
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    s.shadow.inherit = False
    s.text_frame.text = ""
    textbox(x + 16, y + 12, 400, 22, [(label, 13, label_colour, True, False)])
    return s


def box(x, y, w, h, lines, stroke=INK, fill=WHITE, tag=None,
        dash=False, title_size=14, body_size=11.5, name=None):
    s = shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, E(x), E(y), E(w), E(h))
    s.adjustments[0] = 0.10
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.color.rgb = stroke
    s.line.width = Pt(1.4)
    s.shadow.inherit = False
    if dash:
        lnEl = s.line._get_or_add_ln()
        lnEl.append(lnEl.makeelement(qn("a:prstDash"), {"val": "dash"}))
    if name:
        s.name = name

    tf = s.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = Inches(0.05)
    tf.margin_bottom = Inches(0.04)
    tf.vertical_anchor = MSO_ANCHOR.TOP if tag else MSO_ANCHOR.MIDDLE

    idx = 0
    if tag:
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run(); r.text = tag
        r.font.name = FONT; r.font.size = pt(11); r.font.bold = True
        r.font.color.rgb = stroke
        idx = 1
        if lines:
            sp = tf.add_paragraph()
            sp.space_before = Pt(0)
            r = sp.add_run(); r.text = ""
            r.font.size = pt(4)
            idx = 2

    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if (idx == 0 and i == 0) else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = ln
        r.font.name = FONT
        r.font.size = pt(title_size if i == 0 else body_size)
        r.font.bold = (i == 0)
        r.font.color.rgb = INK if i == 0 else MUTED
    return s


TOP, LEFT, BOTTOM, RIGHT = 0, 1, 2, 3


def connect(a, a_site, b, b_site, colour=INK, dashed=False,
            kind=MSO_CONNECTOR.STRAIGHT, width=1.6):
    c = shapes.add_connector(kind, Emu(0), Emu(0), Emu(0), Emu(0))
    c.begin_connect(a, a_site)
    c.end_connect(b, b_site)
    set_arrow(c, colour, dashed, width)
    return c


def free_arrow(x1, y1, x2, y2, colour=INK, dashed=False, width=1.4):
    c = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(x1), E(y1), E(x2), E(y2))
    set_arrow(c, colour, dashed, width)
    return c


# ------------------------------------------------------------------ title
textbox(40, 20, 1300, 34,
        [("APIGUARD — Continuous API Security Assessment in DevSecOps Pipelines",
          21, INK, True, False)], align=PP_ALIGN.CENTER)
textbox(40, 56, 1300, 24,
        [("Rule scanning stays authoritative; the model ranks every endpoint and explains why",
          13, MUTED, False, True)], align=PP_ALIGN.CENTER)

# ------------------------------------------------------------------ runtime
band(30, 92, 1320, 218, BAND, "RUNTIME  ·  in the pipeline", MUTED)

b_spec = box(50, 160, 150, 92, ["OpenAPI spec", "OpenAPI 3.x /", "Swagger 2.0"],
             name="Input spec")
b_s0 = box(230, 160, 165, 92, ["Normaliser", "parse to one", "internal form"],
           tag="S0", name="S0 Normaliser")
b_s1 = box(425, 160, 185, 92, ["Rule scanner", "Spectral + OWASP", "ruleset (2023)"],
           tag="S1", name="S1 Rule scanner")

b_s2 = box(640, 138, 350, 136, [], tag="S2", name="S2 AI verifier")
textbox(640, 152, 350, 22, [("AI verifier", 14, INK, True, False)],
        align=PP_ALIGN.CENTER)
b_s2a = box(650, 176, 100, 78, ["Feature", "builder"], tag="S2a",
            title_size=12.5, body_size=11, name="S2a Feature builder")
b_s2b = box(770, 176, 100, 78, ["XGBoost"], tag="S2b",
            title_size=12.5, body_size=11, name="S2b XGBoost")
b_s2c = box(890, 176, 90, 78, ["SHAP"], tag="S2c",
            title_size=12.5, body_size=11, name="S2c SHAP")

b_s3 = box(1020, 160, 165, 92, ["Risk gate", "score vs threshold τ"],
           tag="S3", name="S3 Risk gate")

textbox(1218, 178, 160, 22, [("pass → exit 0", 12.5, MUTED, False, False)])
textbox(1218, 206, 160, 22, [("fail → exit 1", 12.5, MUTED, False, False)])

connect(b_spec, RIGHT, b_s0, LEFT)
connect(b_s0, RIGHT, b_s1, LEFT)
connect(b_s1, RIGHT, b_s2, LEFT)
connect(b_s2a, RIGHT, b_s2b, LEFT)
connect(b_s2b, RIGHT, b_s2c, LEFT)
connect(b_s2, RIGHT, b_s3, LEFT)
free_arrow(1188, 189, 1212, 189, MUTED, width=1.2)
free_arrow(1188, 217, 1212, 217, MUTED, width=1.2)

# ------------------------------------------------------------------ offline
band(30, 350, 1320, 210, BAND2, "OFFLINE  ·  training", AMBER)

b_t1 = box(50, 414, 165, 92, ["Corpus", "APIs.guru,", "APIstic"], tag="T1",
           name="T1 Corpus")
b_t2 = box(245, 414, 175, 92, ["Labels", "scanner + manual", "+ vulnerable apps"],
           tag="T2", name="T2 Labels")
b_t3 = box(450, 414, 210, 92, ["Shared core", "same S0 + S2a code", "as runtime"],
           tag="T3", stroke=AMBER, name="T3 Shared core")
b_t4 = box(690, 414, 165, 92, ["Trainer", "grouped splits,", "fixed seeds"], tag="T4",
           name="T4 Trainer")
b_model = box(885, 414, 150, 92, ["model.json", "trained artefact"], stroke=AMBER,
              name="model.json")

connect(b_t1, RIGHT, b_t2, LEFT)
connect(b_t2, RIGHT, b_t3, LEFT)
connect(b_t3, RIGHT, b_t4, LEFT)
connect(b_t4, RIGHT, b_model, LEFT)
textbox(560, 524, 420, 22,
        [("retraining is run deliberately, never automatically", 11.5, AMBER, False, False)],
        align=PP_ALIGN.CENTER)

# model.json -> S2b, and T3 -> S0
connect(b_model, TOP, b_s2b, BOTTOM, colour=AMBER, kind=MSO_CONNECTOR.ELBOW)
textbox(878, 300, 200, 22, [("loaded at startup", 12, AMBER, False, False)])

connect(b_t3, TOP, b_s0, BOTTOM, colour=AMBER, dashed=True,
        kind=MSO_CONNECTOR.ELBOW, width=1.4)
textbox(338, 300, 230, 22, [("identical code path", 11.5, AMBER, False, False)])

# ------------------------------------------------------------------ feedback
band(30, 600, 1320, 200, BAND3, "FEEDBACK  ·  human review", TEAL)

b_dev = box(880, 660, 220, 92, ["Developer / analyst", "reviews the verdict"],
            stroke=TEAL, name="Human review")
b_queue = box(520, 660, 250, 92, ["Feedback queue", "feedback.jsonl"], stroke=TEAL,
              name="Feedback queue")

# routed by hand so it clears the model.json box
free_arrow(1102, 254, 1102, 654, TEAL, dashed=True, width=1.4)
connect(b_dev, LEFT, b_queue, RIGHT, colour=TEAL, dashed=True, width=1.4)
connect(b_queue, LEFT, b_t2, BOTTOM, colour=TEAL, dashed=True,
        kind=MSO_CONNECTOR.ELBOW, width=1.4)

textbox(1140, 458, 210, 100,
        [("no arrow from the gate", 12, TEAL, False, False),
         ("back into the model —", 12, TEAL, False, False),
         ("that would train it on", 12, TEAL, False, False),
         ("its own output", 12, TEAL, False, False)])

# ------------------------------------------------------------------ legend
lg1 = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(50), E(836), E(86), E(836))
lg1.line.color.rgb = AMBER; lg1.line.width = Pt(2.0)
textbox(96, 828, 320, 20,
        [("shared code and model artefact", 12, MUTED, False, False)])

lg2 = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(330), E(836), E(366), E(836))
lg2.line.color.rgb = TEAL; lg2.line.width = Pt(2.0)
lnEl = lg2.line._get_or_add_ln()
lnEl.append(lnEl.makeelement(qn("a:prstDash"), {"val": "dash"}))
textbox(376, 828, 300, 20,
        [("human-in-the-loop path", 12, MUTED, False, False)])

textbox(900, 828, 430, 20,
        [("Unit of analysis: one endpoint (path + method)", 12, MUTED, False, False)],
        align=PP_ALIGN.RIGHT)

prs.save("/home/claude/architecture_editable.pptx")
print("ok")
