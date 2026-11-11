# Deliverable 2 audit — APIGUARD System Model
Audited 6 Sep 2026 against `overleaf/main.tex` (686 lines), `refs.bib`, `README.txt`,
`APIGUARD_D2_Overleaf.zip`, `Deliverable2_SystemModel_IEEE.pdf`.

---

## A. Blocking — fix before submitting

### A1. RQ1 is unanswerable as written, and E1 has label leakage
RQ1 asks whether the model "predicts endpoint-level findings more accurately than the
scanner alone." If the labels are L1 (Spectral findings mapped to endpoints), the scanner
is 100% accurate **by construction** — there is nothing to beat.

It gets worse: feature group E (`flagged_by_spectral`, `rule_count`, `severity_max`,
`owasp_categories_hit`) comes from the same tool that produced the label. Under L1, group E
*is* the label. E1 will report a near-perfect PR-AUC that means nothing, and the adviser
will spot it.

**Fix.** Say which label set each experiment uses. Add a "Label source" column to
Table VII. Then either:
- run E1 on L2 + L3 labels only (honest, small), or
- run E1 on L1 with **group E removed**, and reword RQ1 as *"can endpoint-level design
  features reproduce scanner findings without seeing the scanner output?"*

Both are defensible. Silence is not.

### A2. The SHAP contract in Table VI is technically wrong
> "Attributions sum to the score minus the base value."

TreeSHAP on an XGBoost `binary:logistic` model explains the **raw margin (log-odds)** by
default. Attributions sum to `margin − base_margin`, not `probability − base_probability`;
additivity does not survive the logistic transform. It only holds in probability space if
you set `model_output="probability"`, which needs a background dataset and is much slower.

**Fix.** "Attributions sum to the model's log-odds output minus the base value; the risk
score is the logistic transform of that sum."

### A3. Table I contradicts the Deployment View on who controls τ
Table I: developer "cannot change the gate threshold."
Deployment View: `--threshold 0.70 --max-above 0` sits in a GitHub Actions workflow file in
**the same repository the developer pushes to**. They can change it in the same commit.
The threat model then half-admits this ("not a defence against a developer who ... lowers τ"),
which contradicts Table I outright.

**Fix.** Either state the enforcement mechanism (branch protection on `.github/workflows/`,
or an org-level reusable workflow the repo cannot edit), or delete the claim from Table I
and let the threat model carry it.

### A4. The VAmPI citation invents an author name
`refs.bib`: `author = {Gavrilov, Erev0s}`. The repository owner publishes only the handle
**erev0s**; no real name appears anywhere on the repo. "Gavrilov" is not verifiable.

**Fix.** `author = {{erev0s}}` in `refs.bib`, and `erev0s, "VAmPI --- vulnerable REST API."`
in the `thebibliography` block.

*(Everything else about VAmPI checks out: URL `github.com/erev0s/VAmPI` correct, MIT,
`vuln=1/0` switch, OpenAPI 3 specs in `openapi_specs/`. Note `API-Security-Project-Plan.md`
§10 [10] still carries the old wrong URL — fix it when that file is next touched.)*

---

## B. Should fix — a reviewer will ask

| # | Issue | Fix |
|---|---|---|
| B1 | "Must finish in seconds" / "a few seconds for a few hundred endpoints" is asserted as a requirement but **no experiment measures it**. | Add latency reporting: wall-clock per spec, split S1 vs S2b, on a stated machine. Fold into E4 or add E6. |
| B2 | S0 accepts Swagger 2.0 and feature F encodes the version — but `spectral-owasp-ruleset` v2.x is built for the OWASP 2023 edition and documented against OAS 3.x. If it fires fewer rules on OAS2 specs, **L1 labels are biased by spec version, and feature F lets the model learn that bias directly**. | Either restrict the corpus to OAS3, or report per-version rule-firing rates and justify keeping F. |
| B3 | The group C sensitive-term lexicon has no provenance — it is ten hand-picked English words, yet it carries the whole "what a rule cannot see" claim. | State how the lexicon is built, that it is English-only, and how the L2 labellers avoid using the same lexicon they are meant to validate. |
| B4 | No feature count `d`, no expected positive rate. `scale_pos_weight` is mentioned with nothing to set it from. | Give an approximate `d` per group and an expected class balance. |
| B5 | Table I makes the "Security analyst" authoritative for labels; T2 says L2 is labelled by "both team members." The trust model implies an expert who does not exist. | Say plainly that the team plays the analyst role, adviser as tie-breaker. |
| B6 | Adversary model omits **evasion of the model itself**. `model.json` and τ are committed to the repo, so both are fully known. Group D (description length, readability, examples present) is trivially inflatable — write more prose, lower the score. | One sentence: gaming is out of scope because the adversary is external and the developer is assumed non-malicious — and note this is part of why the E5 ablation on group D matters. |
| B7 | Both τ and `k` are in the gate, but only τ is swept (E3). Nothing determines `k`. | State that `k` is a deployment policy knob, not a tuned parameter, and that all reported results use `k=0`. |

---

## C. Cosmetic / consistency

- `--threshold 0.7` (data flow, step 2) vs `--threshold 0.70` (deployment); step 2 also omits
  `--max-above`. Make the two invocations identical.
- Table VII (RQ→experiment) is typeset inside §Design Justifications but introduced in
  §How the System Model Will Be Validated. Move the float or the section.
- §How the System Model Will Be Validated is two short paragraphs and repeats the
  conclusion's forward-look. Merge it into §Design Justifications.
- "2,529 APIs / 108,837 endpoints" needs an inline snapshot date — APIs.guru changes weekly,
  and the corpus section already promises dated snapshots.
- **12 references. CSS453 requires ≥15 for the final report.** Three short.
- `\thanks`: "The research design is unchanged" is a claim about D1 the reader cannot check.
  Prefer "the research questions and method are unchanged; the target artefact changes from
  Terraform code to the OpenAPI specification."

---

## D. Verified clean

- **LaTeX integrity:** 9 `\label`s, 7 `\ref` targets, all resolve. All 12 bib entries are
  cited. No undefined references, no orphan `\bibitem`s.
- **Overleaf packaging:** ZIP is flat at the root (`main.tex`, `refs.bib`,
  `architecture.png`, `README.txt`) — correct for "Upload Project."
- **Equations:** (1) and (2) are mutually consistent, consistent with the `k=0` default, and
  consistent with `--max-above 0`.
- **Ruleset claim:** `@stoplight/spectral-owasp-ruleset` v2.x does implement the OWASP API
  Security Top 10 2023 edition and is MIT — as stated.
- **Structure vs rubric:** entities + trust, notation, per-component I/O, data flow,
  interface contracts, threat model, deployment view, validation map. Nothing a "System
  Model and Description" rubric asks for is missing.

---

## Verdict

The document is structurally complete and the writing is strong — the three design
justifications and the honest scope limit are the best part of it, and they are what will
survive review. The weakness is not presentation, it is **A1**: the evaluation as currently
specified cannot answer RQ1, and E1's headline number would be leakage. Fix A1–A4 (roughly
an hour of editing), and D2 is submission-ready.

---

# Part 2 — What the adviser will actually ask

Added 6 Sep 2026. These are review questions, not document defects. Have an answer ready for
each; the starred ones need a change to `main.tex` because the document currently has no answer
at all.

### Q1. "Your labels come from Spectral. Is your model learning security, or learning Spectral?"
**This is the question the whole project lives or dies on.** Do not let it be asked — answer it
in the abstract and again in the introduction, in one sentence, before he raises it.

Your answer is E2, the rule hold-out: remove one OWASP category from training, see whether the
model still flags endpoints in it. Above-chance recall means the model learned the design
property, not the rule trigger. That is a good answer. But it is currently buried in Table VII,
and item A1 above undercuts it — if E1 also runs on scanner labels *with the scanner features
included*, he will conclude the whole evaluation is circular and stop listening before you get
to E2. Fix A1 first, then this question is your strongest moment.

### Q2.* "Why XGBoost? Why not just hand the spec to an LLM?"
**The document never mentions language models once.** In 2026 this is the first question any
reviewer asks about a "classify this document" project, and having no answer looks like you did
not consider the obvious alternative.

You have a genuinely strong answer — use it:
- A build gate must be **deterministic and reproducible**. `model.json` under version control
  gives byte-identical verdicts; an API-served LLM does not, and cannot be re-run in a year to
  reproduce a reported result.
- **Cost and latency at corpus scale.** 108,837 endpoints × every commit is not an LLM workload.
- **SHAP gives feature-level attribution**; an LLM gives a plausible sentence, which is not the
  same thing and cannot be validated by ablation.
- Nothing stops an LLM being a **baseline** — and adding "LLM zero-shot" as a fourth baseline in
  E1, alongside majority-class, scanner-severity and logistic regression, turns this question
  from a weakness into a contribution.

Add a short paragraph to §Design Justifications as decision 4.

### Q3. "Two undergraduates hand-labelling 300 endpoints for security. Why should I believe those labels?"
Cohen's κ measures whether you two **agree**, not whether you are **right** — you can agree and
both be wrong. Your real answer is the three-tier design: L3 (VAmPI, crAPI) is documented ground
truth that anchors the scale, L2 is calibrated against it, and disagreements go to the adviser as
tie-breaker. Say that explicitly in T2 — right now T2 reports κ and stops, which invites exactly
this question.

### Q4.* "In CI, do you rescan every endpoint on every commit?"
As specified, yes — and that means an existing API with legacy debt fails **every build forever**,
whether or not the commit touched anything relevant. `k` is your only relief and it is a blunt
one: raise it enough to unblock the team and you have also switched off detection of new problems.

The natural design is to gate on **new or changed endpoints** (diff the normalised endpoint set
against the base branch) while reporting on all of them. This is a small addition to S3 and it is
the difference between a tool someone can actually adopt and a demo. **This is the single best
improvement you could make to the system model itself.**

### Q5.* "Eight weeks, five experiments, a corpus, 300 hand labels, and a working CLI. What gets cut?"
The deliverable shows no schedule and no contingency. You have already decided this — cut the
APIstic scale-up and 42Crunch first, never E2 — but it is only in your notes, not in the document.
Two sentences at the end of §How the System Model Will Be Validated stating the priority order
turns "have you thought about feasibility" into "yes, and here it is."

### Q6. "A spec can be secure on paper and the service insecure. So what is this worth?"
You handle this well already — §Assumptions states it plainly and E4 measures it. Keep the honesty;
it is the most credible paragraph in the document. Sharpen the answer to the follow-up ("so a
perfect spec over a terrible service passes your gate — isn't that dangerous?"): APIGUARD is a
**design-review gate, not a security guarantee**, it sits alongside DAST rather than replacing it,
and a spec/implementation mismatch is itself a reportable defect.

### Q7. "What is left that Cheh and Chen did not do?"
Scale (108,837 endpoints vs their 1 API), a learned score rather than a hand-built graph, per-finding
explanation, and a CI gate. You have this — just be able to say it in one breath.

### Q8. "Deliverable 1 described a different system. Where is the updated D1?"
Still outstanding. The `\thanks` note explains the switch, but ask him directly whether he wants a
revised D1 rather than waiting to be asked.

---

## Bottom line on readiness

**Not yet — but it is close.** A1–A4 in Part 1 are about an hour of editing and are the difference
between "well written" and "correct." Q2, Q4 and Q5 above are each a short paragraph and each closes
a hole he will otherwise find.

Do these six, in this order, and submit:
1. A1 — label sources per experiment (also decides the 30 Oct methodology deliverable)
2. A2 — SHAP log-odds wording
3. A3 — who controls τ
4. A4 — VAmPI citation
5. Q2 — the "why not an LLM" paragraph
6. Q4 — gate on changed endpoints only

Q5 (contingency order) is two sentences and worth adding while you are in the file.
