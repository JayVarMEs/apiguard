# Continuous API Security Assessment in DevSecOps Pipelines

**Working tool name:** APIGUARD
**Course:** CSS453 Final Year Project · 8-week plan
**Deliverable:** dissertation + working tool

---

## 1. Problem

Modern systems are assembled out of HTTP APIs, and the OpenAPI specification is where an
API's security posture is first written down: which endpoints require authentication, which
scheme is used, what data comes back, what limits exist. That makes the spec a cheap and
early place to catch security design mistakes — long before a penetration test.

The problem is that spec-level checking today is *rule-based only*. A linter such as Spectral
with the OWASP ruleset fires when a written rule matches. It cannot say which of its findings
actually matter, it produces the same alert whether an endpoint returns a health-check string
or a customer's date of birth, and it is silent about anything nobody wrote a rule for. In a
CI/CD pipeline this shows up as two failures: alert fatigue (developers ignore the gate) and
blind spots (the gate passes something dangerous).

Scale makes this concrete. The APIstic dataset contains 1,275,568 valid OpenAPI
specifications mined from GitHub, SwaggerHub, BigQuery and APIs.guru [1]. The curated
APIs.guru directory alone holds 2,529 API descriptions covering 108,837 endpoints [8]. This
is a large, machine-readable body of real-world API design — and it is almost untouched as
training data for security.

**APIGUARD** puts a supervised model *after* the rule scanner in the pipeline. The scanner
keeps finding what rules find; the model scores every endpoint for security risk, ranks the
findings, and explains each score with SHAP. The CI gate then acts on a risk score rather
than on raw alert counts.

---

## 2. Scope

**In scope**

- Input: OpenAPI 3.x and Swagger 2.0 specification documents.
- Unit of analysis: **one endpoint** (one `path` + `method` operation).
- Static analysis of the specification, not of the server source code.
- Rule scanners: Spectral with `@stoplight/spectral-owasp-ruleset` v2.x (OWASP API Security
  Top 10 2023 edition, MIT licensed) [9], optionally the 42Crunch audit score.
- Model: XGBoost, with SHAP for per-prediction explanation.
- Delivery: a CLI that returns a CI-friendly exit code, plus a GitHub Actions example.

**Out of scope (state this explicitly in the dissertation)**

- Source-code analysis of API implementations.
- GraphQL, gRPC, SOAP.
- Live traffic analysis and WAF-style runtime blocking.
- Dynamic scanning at corpus scale. OWASP ZAP and Schemathesis are used **only** in
  Experiment 4 against two deliberately vulnerable applications, not across the corpus.

**Known limitation to argue honestly:** a specification can be secure on paper while the
implementation behind it is not. APIGUARD measures *design-level* risk. Experiment 4 is what
tests how far that carries into real vulnerable implementations.

**Not a duplicate of Topic 24** (Automatic API Security Design Review for Microservices Using
Threat Graph Analysis). That topic reviews a threat model at design time. This one runs
continuously inside the CI/CD pipeline on every commit and produces a numeric gate decision.
Say this in the introduction.

---

## 3. Research questions

**RQ1 — Feasibility.** Can a supervised model trained on OpenAPI structure, security-scheme
and data-sensitivity features predict security-relevant findings at endpoint level more
accurately than the rule scanner alone?

**RQ2 — Generalisation (the important one).** When an entire class of OWASP API Top 10
findings is removed from the training labels, does the model still flag endpoints in that
class? This is the rule hold-out experiment. It is the defence against the obvious criticism
that "a model trained on Spectral labels has only learned Spectral" — the circularity
problem. Protect this experiment above everything else in the plan.

**RQ3 — False-positive reduction.** Against an L2 sample labelled by an LLM against the OWASP checklist, does risk ranking reduce
the number of findings a developer must read before reaching the real issues, compared with
the scanner's own severity ordering?

---

## 4. Architecture

Three lanes. The runtime lane is what ships; the offline lane trains the model; the feedback
lane is how human verdicts re-enter the system safely.

```
RUNTIME   Input (.yaml / .json spec)
          → S0  Normaliser        parse OpenAPI 3.x / Swagger 2.0 → common internal form
          → S1  Rule scanner      Spectral + OWASP ruleset (+ 42Crunch audit score)
          → S2  AI verifier       S2a feature builder → S2b XGBoost → S2c SHAP
          → S3  Risk gate         score < τ pass, ≥ τ fail → CI exit code

OFFLINE   T1 Corpus (APIs.guru; APIstic not used)
          → T2 Labels (scanner findings + manual sample + vulnerable-app ground truth)
          → T3 Shared core   (S0 + S2a — the SAME code as runtime, imported not copied)
          → T4 Trainer → model.json → loaded by S2b at startup

FEEDBACK  S3 → developer / analyst reviews verdict
             → feedback queue (feedback.jsonl)
             → T2 Labels        (takes effect only at the next deliberate retrain)
```

Three design decisions worth defending in the write-up:

**The model sits after the scanner, not instead of it.** Rules stay authoritative for what
they cover; the model adds ranking and covers what rules miss. This is the same arrangement
used by Flynn et al. for prioritising alerts from multiple static analysis tools with
classification models [5], and it avoids the weaker "ML replaces the linter" design.

**S2 scores every endpoint, not only flagged ones.** Scanner findings enter as *features*
(`flagged_by_spectral`, `rule_count`, `severity_max`, `owasp_categories_hit`) which are simply
zero for unflagged endpoints. This costs nothing and is what keeps RQ2 answerable — an
endpoint no rule fired on can still be scored high.

**The feedback loop does not reach the model directly.** Human verdicts land in a queue and
enter through T2 Labels at the next retrain. A dashed arrow from the gate back into the model
would mean the model trains on its own output.

---

## 5. Feature design — the core technical contribution

This is stage S2a and it is where the marks are. Six groups, all computed from the normalised
spec. The APIstic metric catalogue [1] is a useful starting point for the structural group;
the sensitive-data group is inspired by Cheh and Chen's field-exposure analysis [2].

**A. Structural**
path depth · number of path parameters · path parameter looks like an object identifier
(`id`, `uuid`, `_id` patterns — the API1 Broken Object Level Authorization signal) · HTTP
method (one-hot) · query/header parameter counts · request body present · response schema
property count · number of declared status codes · are 401/403 declared · deprecated flag

**B. Security scheme**
endpoint has a security requirement · inherits global security vs overrides it · scheme type
one-hot (apiKey / http-basic / http-bearer / oauth2 / openIdConnect) · scope count · server
URL uses `http` rather than `https`

**C. Data sensitivity**
count of response property names matching a sensitive-term lexicon (password, token, secret,
ssn, dob, phone, email, address, card, balance) · maximum term weight · sensitive properties
in response vs request · ratio of sensitive to total properties · combination flag: no
security requirement **and** sensitive response properties

**D. Documentation hygiene**
description and summary length · example present · readability index · version segment in
path · pagination parameters present · rate-limit headers documented

**E. Scanner-derived (zero when nothing fired)**
`flagged_by_spectral` · `rule_count` · `severity_max` · `owasp_categories_hit` ·
`42crunch_audit_score` (optional)

**F. Context**
endpoint count of the parent spec · OpenAPI 3 vs Swagger 2 · provider/domain category

Group E is deliberately separable so the ablation in Experiment 5 can show how much the model
contributes *without* any scanner signal at all.

---

## 6. Data plan

**Corpora**

| Source | Size | Use |
|---|---|---|
| APIs.guru directory [8] | 2,529 APIs / 108,837 endpoints | primary, curated and clean |
| APIstic [1] | 1,275,568 specs | not used in this project; cited as a metric reference only |
| VAmPI [10] | 1 API, vulnerable **and** secure mode | ground-truth pair for Experiment 4 |
| OWASP crAPI [11] | 1 API, documented challenges | second ground-truth target |

VAmPI is unusually valuable: the same API ships in vulnerable and secure configurations with
an OpenAPI 3 spec, so it yields matched positive/negative examples rather than guesses.

**Labels**

- **L1 automatic** — Spectral OWASP findings mapped down to the endpoint they belong to.
  Cheap, plentiful, and circular if used alone. Pin the ruleset version.
- **L2 reference** — a stratified sample of 304 endpoints labelled by three LLM passes using the OWASP
  API Top 10 2023 definitions, majority vote, agreement reported as Cohen's/Fleiss' κ. No human labels
  (decision 2026-11-10). Small but independent of the scanner, which is what makes RQ3 credible.
- **L3 ground truth** — VAmPI and crAPI endpoints with known, documented vulnerabilities.

**Splitting rule — do not get this wrong.** Split by **provider / repository**, never
randomly. Public API specs are heavily copy-pasted and templated; a random split leaks
near-identical endpoints across train and test and produces impressive fake scores. Also
de-duplicate by normalised spec hash before splitting.

**Reproducibility.** Pin Spectral and ruleset versions, record the corpus snapshot date,
commit `requirements.txt`, and fix all random seeds. Scanner version drift silently changes
every label.

---

## 7. Evaluation

**E1 — Feasibility (RQ1).** Provider-grouped 5-fold cross-validation on the APIs.guru corpus.
Report PR-AUC, F1 and MCC — not plain accuracy, the classes are very imbalanced. Baselines:
majority class, scanner-severity ordering, and logistic regression on the same features.

**E2 — Rule hold-out (RQ2). The headline experiment.** Remove one OWASP 2023 category from
the training labels entirely (start with API2 Broken Authentication, repeat for API1, API4 and
API9). Train, then measure recall on exactly the endpoints belonging to the held-out category.
Above-chance recall means the model learned something about the underlying design property
rather than memorising a rule's trigger.

**E3 — Analyst effort (RQ3).** On the L2 LLM-labelled sample, measure precision@k and the
number of findings read before reaching all true positives, comparing APIGUARD ranking against
scanner severity ordering. Sweep the gate threshold τ on the validation set and report the
precision/recall trade-off curve.

**E4 — External validity.** Run the trained model on VAmPI and crAPI. Does it rank the known
vulnerable endpoints above the benign ones, and does VAmPI's secure mode score lower than its
vulnerable mode? This is also the only place ZAP and Schemathesis are used, to confirm the
flagged endpoints really are exploitable.

**E5 — Ablation and explanation.** Retrain with each feature group removed to show which group
carries the signal, especially with group E (scanner features) removed. Report global SHAP
importance and two or three worked per-endpoint SHAP explanations for the dissertation.

---

## 8. Eight-week schedule

| Week | Goal | Done when |
|---|---|---|
| 1 | S0 normaliser + corpus download; both spec versions parse into the common form | 100% of the APIs.guru corpus parses or fails with a logged reason |
| 2 | S2a feature builder (groups A–D) + unit tests | feature table produced for every endpoint, no nulls |
| 3 | S1 scanner integration, L1 labels, provider-grouped splitter, de-duplication | labelled dataset frozen and version-pinned |
| 4 | T4 trainer, first XGBoost model, **E1** | E1 numbers in a table, baselines beaten |
| 5 | **E2 rule hold-out** — protect this week | recall on held-out categories reported |
| 6 | L2 LLM labelling (done) + **E3**; S3 gate and CLI exit codes | κ reported, τ chosen, CLI runs end to end |
| 7 | **E4** on VAmPI and crAPI; **E5** ablation + SHAP; GitHub Actions example | all five experiments complete |
| 8 | Dissertation writing, figures, demo, buffer | draft submitted |

Weeks 1–3 are plumbing and are the ones that always overrun. If the schedule slips, cut the
APIstic scale-up and the 42Crunch integration first — never E2.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Label circularity (model just relearns Spectral) | E2 rule hold-out; report it as the headline result |
| Data leakage from duplicated specs | hash de-duplication + provider-level splits |
| Severe class imbalance | `scale_pos_weight`, PR-AUC not accuracy, stratified folds |
| Spec ≠ implementation | scope statement in §2; E4 tests the link empirically |
| Scanner version drift changes labels | pin versions, record snapshot date |
| Labels are noisy | LLM labels from 3 passes, majority vote, L3 as external anchor |
| Dynamic scanning eats the schedule | ZAP/Schemathesis confined to E4 only |

---

## 10. References

[1] S. Serbout and C. Pautasso, "APIstic: A Large Collection of OpenAPI Metrics," in *Proc.
21st Int. Conf. on Mining Software Repositories (MSR)*, 2024, pp. 265–277.
doi:10.1145/3643991.3644932

[2] C. Cheh and B. Chen, "Analyzing OpenAPI Specifications for Security Design Issues," in
*2021 IEEE Secure Development Conf. (SecDev)*, 2021, pp. 15–22. doi:10.1109/SecDev51306.2021.00019

[3] F. Tanveer, F. Iradat, W. Iqbal, and A. Ahmad, "Towards Secure APIs: A Survey on RESTful
API Vulnerability Detection," *Computers, Materials & Continua*, vol. 84, no. 3, pp.
4223–4257, 2025. doi:10.32604/cmc.2025.067536

[4] A. Decrop, M. Vandeloise, P. Heymans, and G. Perrouin, "OASQuali: Automated Quality
Analysis of OpenAPI Specifications," in *Int. Conf. on Web Engineering (ICWE)*, 2026, pp.
94–108. doi:10.1007/978-3-032-29372-5_7

[5] L. Flynn, W. Snavely, D. Svoboda, N. VanHoudnos, R. Qin, J. Burns, D. Zubrow, R. Stoddard,
and G. Marce-Santurio, "Prioritizing alerts from multiple static analysis tools, using
classification models," in *Proc. 1st Int. Workshop on Software Qualities and Their
Dependencies (SQUADE)*, 2018, pp. 13–20. doi:10.1145/3194095.3194100

[6] T. Chen and C. Guestrin, "XGBoost: A Scalable Tree Boosting System," in *Proc. 22nd ACM
SIGKDD Int. Conf. on Knowledge Discovery and Data Mining*, 2016, pp. 785–794.

[7] S. M. Lundberg and S.-I. Lee, "A Unified Approach to Interpreting Model Predictions," in
*Advances in Neural Information Processing Systems 30 (NeurIPS)*, 2017, pp. 4765–4774.

[8] APIs.guru, "OpenAPI Directory." [Online]. Available: https://apis.guru/

[9] Stoplight, "spectral-owasp-ruleset." [Online]. Available:
https://github.com/stoplightio/spectral-owasp-ruleset

[10] VAmPI — Vulnerable REST API. [Online]. Available:
https://github.com/erev0s/VAmPI

[11] OWASP crAPI — completely ridiculous API. [Online]. Available: https://github.com/OWASP/crAPI

[12] OWASP, "API Security Top 10 — 2023." [Online]. Available:
https://owasp.org/API-Security/editions/2023/en/0x11-t10/

*References [1]–[5] were verified against Crossref and the publishers' own PDFs on 25 Aug 2026.
[6] and [7] are already downloaded in `references/`.*
