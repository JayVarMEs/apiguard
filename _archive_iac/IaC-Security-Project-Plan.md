# AI-Based Infrastructure-as-Code Security Verification
### Final Year Project Plan — 8 Weeks

**Target:** Terraform (HCL) · **Model:** XGBoost · **Output:** Dissertation + working tool

---

## 1. The one-sentence version

> Build a machine learning model (XGBoost) that reads Terraform code and predicts
> whether a resource is insecure — then show whether it can find problems that
> rule-based scanners like Checkov and tfsec miss.

That last part is the whole point. Anyone can wrap a scanner. The research
question is whether learning *generalises* beyond hand-written rules.

---

## 2. Why this problem is worth studying

Terraform describes cloud infrastructure as text files. One wrong line — a public
S3 bucket, an open security group, an unencrypted database — becomes a real,
exploitable cloud misconfiguration the moment it is applied.

Today the standard defence is **rule-based static scanners**: Checkov, tfsec/Trivy,
KICS, Terrascan. They work by pattern matching against a list of known-bad
configurations. This gives them three well-documented weaknesses:

| Weakness | What it means |
|---|---|
| **Zero recall on unknown patterns** | If nobody wrote a rule for it, the scanner cannot see it. |
| **High false positive rate** | Rules ignore context, so developers get alert fatigue and start ignoring findings. |
| **No severity awareness** | A public bucket holding test data and one holding customer PII look identical. |

Machine learning is attractive here because it can learn *combinations* of
properties rather than single hard-coded conditions. That is the gap this project
sits in.

---

## 3. Research questions

Pick RQ1 + RQ2 as your core. RQ3 is your stretch contribution.

**RQ1 — Feasibility**
Can an XGBoost classifier trained on structural features of Terraform resources
detect insecure configurations with accuracy comparable to rule-based scanners?

**RQ2 — Generalisation (the important one)**
When a class of misconfiguration is **removed from the training labels**, can the
model still detect it? In other words: does it learn security, or does it just
memorise Checkov?

**RQ3 — Practical value**
Does combining the model with a rule engine reduce false positives compared to
the rule engine alone?

> **Read RQ2 carefully.** It is the difference between a pass and a distinction.
> See section 9 (Risk 1).

---

## 4. What already exists (related work)

You need this section in the dissertation anyway, so collect it in week 1.

**Rule-based tools** — Checkov (Prisma/Palo Alto), tfsec (now folded into Trivy),
KICS (Checkmarx), Terrascan (Tenable). Study how their rule format works; you will
reuse their rule sets as your label source.

**GLITCH** (Saavedra & Ferreira, ASE 2022) — a technology-agnostic framework that
converts Puppet/Ansible/Chef/Terraform into a shared intermediate representation
and detects security smells on it. Its **replication package includes a manually
labelled oracle dataset** — this is the single most valuable thing you can borrow.
Manually labelled IaC data is otherwise very hard to get.

**TerraMetrics** (stilab-ets) — extracts quality metrics from Terraform. Useful as
a ready-made feature extractor; saves you writing an HCL parser from scratch.

**TerraSecure** (open-source student project) — already does roughly "XGBoost +
rules + LLM" on Terraform and reports 92.45% accuracy. **Do not panic at this.**
Read it closely and note its weaknesses in your related work: it trains on only
**265 samples** derived from a handful of famous breaches, and does not test
generalisation to unseen rule classes. Your contribution is doing this at proper
scale with a proper evaluation. Cite it, then beat it.

**LLM approaches** — several 2025–26 papers apply LLMs to IaC smell detection and
to reducing false positives in static analysis. Worth one paragraph as an
alternative paradigm, and worth one experiment if time allows (see stretch goals).

---

## 5. Method

### 5.1 Data collection (week 2)

Mine public Terraform from GitHub via the GitHub API:

- Search repositories containing `.tf` files, filter by stars/activity to avoid junk
- Target **~2,000–5,000 repositories**, giving roughly **50,000–200,000 resource blocks**
- Deduplicate aggressively — Terraform is heavily copy-pasted, and near-identical
  files across repos will leak between your train and test sets and inflate your scores
- Record repo name, commit hash, file path and licence for every file (needed for
  reproducibility and ethics)

**Unit of analysis: one Terraform `resource` block.** Not one file, not one repo.
This keeps labels clean and gives you enough samples.

### 5.2 Labelling (week 3)

You cannot hand-label 100,000 blocks in 8 weeks. Use a three-tier strategy:

| Tier | Source | Size | Purpose |
|---|---|---|---|
| **Weak labels** | Run Checkov + Trivy over the corpus; a block flagged by either is `insecure` | Full corpus | Training data |
| **Gold labels** | GLITCH oracle + your own manual review of a random sample | ~500 blocks | Honest test set |
| **Synthetic labels** | Take secure blocks and mutate them (remove encryption, open a CIDR to 0.0.0.0/0, widen an IAM policy) | ~2,000 blocks | Controlled generalisation testing |

Two scanners rather than one matters: where they disagree you get a natural
"ambiguous" set, which is interesting material for your discussion chapter.

### 5.3 Feature engineering (week 3) — this is where your marks are

XGBoost works on tables of numbers, not on code. Converting Terraform into good
features **is your technical contribution**. Parse HCL with the `python-hcl2`
library, then extract per resource block:

**Structural**
- resource type (one-hot or target-encoded: `aws_s3_bucket`, `aws_security_group`, …)
- number of attributes, nesting depth, number of blocks inside
- count of variable references, `count`/`for_each` usage, module depth

**Security-semantic** (the valuable ones)
- encryption attributes present/absent, KMS key referenced or default
- any CIDR equal to `0.0.0.0/0`; count of open ports; port ranges touching 22/3389/3306
- IAM policy breadth: count of `"*"` in Action / Resource / Principal
- `public_access_block` present? versioning? MFA delete?
- logging and monitoring attributes present
- any attribute whose value looks like a hardcoded secret (entropy-based check)

**Contextual**
- tags present (e.g. `Environment = production`)
- name/identifier keywords suggesting sensitive data (`prod`, `customer`, `payment`, `backup`)
- provider and region
- how many other resources reference this one (a small dependency-graph feature)

Aim for **80–150 features**. Write the extractor as a standalone, tested module —
you will show its output table in the dissertation.

### 5.4 Modelling (weeks 4–5)

- **Baselines first:** majority class, logistic regression, random forest. You need
  these so XGBoost's numbers mean something.
- **XGBoost:** tune with Optuna or grid search. Handle class imbalance with
  `scale_pos_weight`, not by naively oversampling.
- **Split by repository, never randomly.** Random splits leak copy-pasted code
  between train and test and will give you a fake 99%.
- **Explainability:** run SHAP. Feature importance plots are cheap to produce and
  make an excellent dissertation chapter — and they directly answer "is the model
  reasoning about security or about surface artefacts?"

### 5.5 Evaluation (week 6)

Report **precision, recall, F1, PR-AUC and MCC**. Do not lead with accuracy — with
imbalanced data it is close to meaningless.

Run these four experiments:

1. **Head-to-head** — model vs Checkov vs tfsec on the gold-labelled test set
2. **Rule hold-out (RQ2)** — remove all labels for one misconfiguration class
   (e.g. every public-S3 rule) from training, then test whether the model still
   detects it. Repeat for 5 classes. *This is your headline result either way:*
   if it generalises you have a real finding; if it does not, you have an honest
   negative result about the limits of rule-derived supervision, which is also
   publishable-quality work.
3. **Mutation testing** — measure detection rate on the synthetic mutated blocks
4. **Hybrid (RQ3)** — union and intersection of model + rules; measure the
   false-positive change

---

## 6. System architecture

This is your own design, tightened up. The shape you drew — **normalise → rule scan
→ AI verify → risk gate** — is correct, and in one important way it is better than
a design that tries to replace the scanners outright.

### What your sketch already gets right

- **S0 as a normaliser is a strong idea.** Converting different IaC languages into
  one common structure before analysing it is exactly what GLITCH does, and it is
  what lets you claim the approach is not Terraform-specific.
- **Putting the model *after* the rule scanner sidesteps the circularity trap.**
  The model is not competing with Checkov, it is scoring and prioritising what
  Checkov found. That reframes the contribution as false-positive reduction and
  risk ranking — a claim you can actually defend.
- **The risk gate gives you a real deliverable.** Pass/fail with an exit code is
  the thing that plugs into CI. It makes the demo concrete and gives you a clean
  evaluation target.
- **SHAP in the loop from the start.** Most student projects bolt explainability on
  at the end. Having it in the architecture means every finding carries its reasons.

### The pipeline

```
RUNTIME · tfguard scan
──────────────────────
 ┌──────────┐   ┌──────────────┐   ┌───────────────┐   ╔═══════════════╗   ┌──────────┐
 │ Input    │──▶│ S0           │──▶│ S1            │──▶║ S2            ║──▶│ S3       │
 │ *.tf     │   │ Normaliser   │   │ Rule scanner  │   ║ AI verifier   ║   │ Risk gate│
 │ *.yaml   │   │ python-hcl2  │   │ Checkov·Trivy │   ║ ┌───────────┐ ║   │          │
 │          │   │ PyYAML       │   │ tfsec ·KICS   │   ║ │S2a feature│ ║   │ low →pass│
 └──────────┘   │ → common IR  │   │               │   ║ │  builder  │ ║   │ high→fail│
                └──────────────┘   └───────────────┘   ║ ├─────┬─────┤ ║   │ exit 0/1 │
                                                       ║ │S2b  │S2c  │ ║   └────┬─────┘
                                                       ║ │XGB  │SHAP │ ║        │
                                                       ║ └─────┴─────┘ ║        │
                                                       ╚═══════▲═══════╝        │
                        ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ┘
                        │            loaded at startup        │      analyst reviews
OFFLINE · build once    ▼                                     │      each finding
────────────────────  (into T2)                               │
 ┌──────────┐   ┌──────────────┐   ╔═══════════════╗   ┌──────┴───────┐   ┌──────────┐
 │ T1       │──▶│ T2           │──▶║ T3            ║──▶│ T4           │──▶│model.json│
 │ Corpus   │   │ Labels       │   ║ Shared core   ║   │ Trainer      │   │ booster +│
 │ ~3k repos│   │ weak: S1 out │   ║ S0 + S2a      ║   │ XGBoost      │   │ features │
 │ deduped  │   │ gold: 500 by │   ║ THE SAME CODE ║   │ split by repo│   │ + pinned │
 │          │   │       hand   │   ║ as runtime    ║   │ Optuna       │   │  versions│
 └──────────┘   └──────▲───────┘   ╚═══════════════╝   └──────────────┘   └──────────┘
                       │
                ┌ ─ ─ ─┴─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐
                │  FEEDBACK QUEUE · feedback.jsonl · analyst TP/FP verdicts│
                │  new labels — applied only at the next deliberate retrain│
                └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

The two double-walled boxes are the same code running in both places — that is what
keeps training and scanning from drifting apart. Note where the feedback loop lands:
**not** back into S2, but into the offline label store, so an analyst's verdict only
takes effect at the next deliberate retrain.

A print-quality version of this figure is in `architecture.svg` / `architecture.png`,
ready to drop into the dissertation.

### Four things the sketch was missing

**1 · No training pipeline — must add.**
Your diagram shows only what happens when someone runs the tool. But XGBoost has to
be trained on something first, and that pipeline is most of your dissertation: where
the corpus comes from, how blocks get labelled, how you split train and test. It is
now the bottom lane. Without it, an examiner reading the diagram cannot tell where
the intelligence came from.

**2 · The feature builder was invisible — must add.**
Between S1 and XGBoost something has to turn a resource block plus its scanner
findings into a row of numbers. That step is not plumbing — **it is your main
technical contribution**, and it is where most of your marks live. It gets its own
box inside S2, and it is written once and reused by the trainer.

**3 · The feedback loop needs a definition — clarify.**
Your dashed "check answer" arrow is a good instinct, but as drawn it is ambiguous,
and an examiner will ask what it does. If the gate's own output feeds back into the
model automatically, the system trains on its own predictions and drifts —
indefensible. Define it as **human-in-the-loop**: an analyst marks a finding as a
true or false positive, that verdict is *queued* as new labelled data, and it is
only ever applied at the next deliberate retrain. Say this explicitly in the
dissertation; it turns a weak point into a design decision.

**4 · Two input languages is a scope risk — cut back.**
Terraform *and* Kubernetes YAML means two feature sets, two rule mappings and twice
the labelling — in eight weeks. Keep S0's interface generic so both *could* plug in,
write the YAML adapter only if weeks 1–6 finish early, and **evaluate Terraform
only**. "The design is language-agnostic; this study evaluates Terraform" is a
perfectly respectable sentence.

### One design question to settle first

Does S2 see *only* the resources S1 flagged, or *every* resource?

| Option | What you can claim | Cost |
|---|---|---|
| Flagged only | False-positive reduction and risk ranking. Cannot ever find what the rules missed. | Simplest |
| **All resources (recommended)** | Both of the above *and* detection of misconfigurations no rule covers — which keeps RQ2 alive. | Almost none |

Take the second. S1's findings become *extra features* on every resource —
`flagged_by_checkov`, `severity_max`, `rule_count` — sitting alongside the code
features. Resources nobody flagged simply have those features set to zero, and the
model can still score them. Architecturally it costs you nothing and it doubles what
your project can claim.

### Component responsibilities

| Stage | Does | Built in |
|---|---|---|
| **S0 · Normaliser** | Parse `.tf` with `python-hcl2` into a common block structure. **Shared with training.** | Week 3 |
| **S1 · Rule scanner** | Run Checkov and Trivy; map findings back to blocks; record scanner disagreement | Week 3 |
| **S2a · Feature builder** | Block + findings → fixed-length numeric vector, ~120 features. **Shared, and versioned.** | Week 3 |
| **S2b · XGBoost** | Load `model.json`, score every resource 0–1 | Week 4 |
| **S2c · SHAP** | Per-finding attribution: which features drove this score | Week 5 |
| **Risk gate** | Threshold the score; emit text / JSON / SARIF; set the process exit code | Week 7 |
| **Corpus + labels** | Mine GitHub, deduplicate, keep provenance; weak labels from S1, 500 gold by hand | Weeks 2–3 |
| **Trainer** | Repo-level split, class weighting, Optuna; emits `model.json` + feature list | Weeks 4–5 |
| **Evaluator** | The four experiments; writes metrics and figures into the results chapter | Week 6 |

> **Version the feature list inside the model file.** On startup, S2 compares the
> feature builder's current output names against the ones baked into `model.json`
> and refuses to run if they differ. Pin the Checkov and Trivy versions in there too
> — rule sets change between releases, which silently changes your features. Twenty
> lines of code; saves you a whole category of results you cannot explain.

### Repository layout

```
tfguard/
├── tfguard/              # installable package — the runtime path
│   ├── s0_normalise.py   # HCL/YAML → common blocks     ● shared
│   ├── s1_rules.py       # Checkov + Trivy runner, findings → blocks
│   ├── s2_features.py    # blocks + findings → vector   ● shared
│   ├── s2_model.py       # load model.json, predict, SHAP
│   ├── gate.py           # threshold, exit code
│   ├── report.py         # text, JSON, SARIF output
│   └── cli.py            # entry point: tfguard scan
├── pipeline/             # offline only — not shipped to users
│   ├── mine.py           # GitHub crawler
│   ├── label.py          # weak labels via s1_rules, gold merge
│   ├── train.py          # XGBoost + Optuna, repo-level split
│   └── evaluate.py       # the four experiments
├── data/                 # gitignored; parquet on disk, no database
│   ├── corpus.parquet
│   ├── features.parquet
│   ├── gold.csv          # your 500 hand labels
│   └── feedback.jsonl    # queued analyst verdicts, applied only on retrain
├── models/
│   └── model.json        # booster + feature list + scanner versions
├── results/              # figures and tables, written by evaluate.py
└── tests/                # S0 and S2a unit tests — test these two hardest
```

### Stack

- **Python 3.11** — `python-hcl2`, `PyYAML`, `pandas`, `pyarrow`, `scikit-learn`,
  `xgboost`, `shap`, `optuna`, `typer` for the CLI
- **Checkov** and **Trivy** as external binaries, **pinned to exact versions** — an
  unpinned scanner upgrade silently rewrites your labels mid-project
- **Storage:** parquet files on disk. No database. You do not need one, and standing
  one up costs a week you do not have.
- **Reproducibility:** fix every random seed; log tool versions and the corpus commit
  hash into `results/` on every run

---

## 7. The tool

Keep it small. The dissertation is the deliverable; the tool proves it works.

```
tfguard scan ./infrastructure/

  aws_s3_bucket.customer_data       RISK 0.94   main.tf:23
    → no public_access_block, no encryption, name suggests sensitive data
    → top factors: public_access_block_absent (+0.31), sse_absent (+0.28)

  aws_security_group.web            RISK 0.71   network.tf:11
    → ingress 0.0.0.0/0 on port 22

  Scanned 47 resources · 2 high risk · 5 medium · 1.3s
```

- Python CLI, `pip install -e .`
- Outputs human-readable text **and** JSON/SARIF (SARIF gets you GitHub Actions
  integration almost free — good for a demo, and one screenshot in the report)
- Per-finding SHAP explanation, so it is not a black box
- Optional GitHub Action wrapper as a stretch item

---

## 8. Eight-week timeline

| Week | Focus | Concrete output by Friday |
|---|---|---|
| **1** | Literature + setup | 15–20 papers read and summarised; repo, env, tooling ready; GLITCH package downloaded and running |
| **2** | Data collection | GitHub miner working; deduplicated corpus of Terraform files stored with metadata |
| **3** | Labels + features | Scanners run over corpus; feature extractor producing a clean CSV/parquet table |
| **4** | Baselines + first model | Baselines and a first XGBoost result; *midpoint checkpoint with supervisor* |
| **5** | Tuning + SHAP | Tuned model; SHAP analysis; results chapter figures started |
| **6** | Evaluation experiments | All four experiments run; results tables final. **Feature freeze — no new ideas after this point.** |
| **7** | Tool + writing | CLI packaged and demoable; dissertation full draft |
| **8** | Finish | Revisions, proofreading, submission. Buffer for the week that goes wrong |

**Ground rules that protect the timeline**

- **Everything writes as it goes.** Do not save writing for week 7. Draft the
  method chapter in week 3 while it is fresh; it will be more accurate too.
- **Week 6 is a hard feature freeze.** Late ideas go in "Future Work", not in code.
- **Results before polish.** A working ugly model in week 4 beats a beautiful
  pipeline with no numbers in week 6.
- Show your supervisor something every week, even if it is broken.

---

## 9. Risks — read this section twice

**Risk 1 — Circular reasoning (the big one).**
If you train on Checkov's labels and then evaluate against Checkov, you have
built an expensive Checkov imitator and proven nothing. Your examiner *will* ask
about this. Defences: the gold-labelled test set, the rule hold-out experiment,
and the mutation tests. Address it head-on in your dissertation rather than
hoping nobody notices — naming your own limitation is what makes it look like
research instead of a coding exercise.

**Risk 2 — Data leakage from copy-paste.**
Terraform is copied between repos constantly. Split by repository and deduplicate
on normalised block content, or your scores will be fiction.

**Risk 3 — Severe class imbalance.**
Most resource blocks are fine. Expect 5–15% positives. Use PR-AUC, weight the
classes, and never report accuracy alone.

**Risk 4 — Scope creep.**
Multi-cloud, Kubernetes, an LLM component, a web dashboard — all tempting, all
fatal in 8 weeks. AWS Terraform only. Everything else is Future Work.

**Risk 5 — Ethics and legal.**
You are mining public repositories. Record licences, never publish anything that
looks like a real credential or an exploitable configuration tied to an
identifiable organisation, aggregate your results, and check whether your
department needs an ethics form. Do this in week 1, not week 7.

---

## 10. Stretch goals (only if weeks 1–6 finish on schedule)

- LLM comparison: give the same blocks to an LLM and compare against XGBoost —
  a genuinely current research angle and a strong extra results section
- Cross-cloud test: train on AWS, test on Azure resources
- Temporal analysis: mine commit history to see whether misconfigurations get fixed
- Ensemble: XGBoost + rules + LLM voting

---

## 11. What to do first (next 3 days)

1. Confirm the scope with your supervisor — especially RQ2, which is the part that
   makes this research rather than tool-building
2. Create the Git repo and get Checkov, Trivy and `python-hcl2` installed and running
3. Download the GLITCH replication package and confirm the oracle data is usable
4. Manually label 30 Terraform resource blocks yourself. This is boring and it is
   the highest-value thing you can do this week — it tells you what is actually
   hard about the problem before you commit to a feature set

---

## Sources

- GLITCH: <https://arxiv.org/abs/2205.14371> · <https://github.com/sr-lab/GLITCH>
- GLITCH replication package: <https://github.com/sr-lab/GLITCH-ASE22-Replication-Package>
- Terraform GLITCH replication package: <https://figshare.com/articles/thesis/terraform-GLITCH-replication-package_zip/24574234>
- TerraMetrics: <https://github.com/stilab-ets/terametrics> · <https://dl.acm.org/doi/10.1145/3643916.3644439>
- TerraSecure (XGBoost prior work): <https://github.com/JashwanthMU/TerraSecure>
- Scanner comparisons: <https://policyascode.dev/guides/checkov-vs-tfsec-vs-terrascan/> · <https://devdosvid.blog/2024/04/16/a-deep-dive-into-terraform-static-code-analysis-tools-features-and-comparisons/>
- Reducing false positives in static analysis with LLMs: <https://arxiv.org/html/2601.18844v1>
