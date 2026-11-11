# APIGUARD — advisor demo script (S0)

**One command:** `demo\demo.bat` from `C:\cyberProject`. It runs the three parts below
with a pause between each. Total time: about 6 minutes.

Before the meeting: run it once, so nothing surprises you, and leave the architecture
figure (`architecture.png`, Figure 1 of D2) open in a second window.

---

## Opening line (20 seconds)

> "Deliverable 2 defined four runtime components, S0 to S3. I've implemented S0, the
> normaliser, with its contract tests, and I can run it on the real VAmPI spec and on
> real APIs from the APIs.guru corpus. This is the input every later component depends on."

Point at S0 in the figure. Say where the other three are: **not started, next is S2a**,
which lives in the same package because it is shared with the training lane T3.

---

## Part 1 — The tests (1 minute)

Run first, before showing any output. Nine tests, all passing.

> "These are not unit tests of convenience. Each one is a line from the interface-contract
> table in Deliverable 2."

Name three:

- every endpoint appears exactly once
- an unparsable spec is logged, never silently dropped
- a circular `$ref` is cut, so expansion always terminates

---

## Part 2 — VAmPI (3 minutes)

`python demo\run_s0_demo.py`. Six sections; talk about three of them.

**Section 2, the endpoint table.** 14 endpoints out of the file.

> "One row per path-and-method. That is the unit of analysis fixed in D2."

**Section 3.** This is the moment of the demo. Read it out:

> "Four endpoints have no security requirement and still return sensitive fields.
> `GET /users/v1/_debug` is unauthenticated and returns every user's password and admin
> flag. S0 sees that from the specification alone, before any scanner runs."

Then say why it matters for the design:

> "This is why S2 scores every endpoint, not only the ones the scanner flags. If the model
> only ranked scanner alerts, it could never find this."

**Section 5.** The same endpoint from an OpenAPI 3 file and a Swagger 2.0 file.

> "Same operation id, same security source, same server, same expanded response fields.
> The Swagger 2 body parameter became a request body, and the path-level parameter was
> merged into the operation. After S0, nothing downstream knows which format it came from."

If there is one field to point at, point at **`security_source`**:

> "`inherited` means the operation is silent and the global rule applies. `override_none`
> means it declares `security: []` and switches authentication off deliberately. Those are
> different risks, so I keep them apart. Collapsing them would destroy the signal before
> the feature builder ever sees it."

---

## Part 3 — Real corpus (1 minute)

`python -m apiguard.core.normalizer demo\specs\apis_guru_sample ... --stats`

```
[S0] specs parsed=12 failed=0 (0.00% parse-failure) endpoints=222
```

> "Twelve real APIs from APIs.guru — AWS, Azure, Google, Microsoft. 222 endpoints,
> no parse failures. 139 of those endpoints came from OpenAPI 3 files and 83 from
> Swagger 2.0 files, and they are in one identical form. The full corpus is 2,529 APIs;
> it is the same command with `--all`."

Show `tools\fetch_apis_guru.py` for one sentence:

> "It saves one folder per provider, which is exactly the grouping the provider-grouped
> splits in experiment E1 need, and it writes a manifest with the source URL and snapshot
> date of every file for the report."

---

## Close (20 seconds)

> "Next is S2a, the feature builder, in the same shared core so training and inference
> cannot drift apart. Then S1, the Spectral wrapper. The methodology deliverable is due
> 30 October, and this code is the concrete half of it."

---

## Questions to expect

**"Isn't this just a parser?"**
> "The parsing is the easy part. The value is in the contract: exactly once, never
> silently dropped, always terminates, and one form for both spec versions. Without that,
> the corpus statistics in the report would not be honest, and RQ2 would not be answerable."

**"Where is the machine learning?"**
> "S2. S0 is deliberately dumb — it stays purely structural and makes no judgement. The
> sensitive-word lexicon belongs to S2a, not here."

**"How do you know the output is correct?"**
> "Two ways. The nine contract tests, and the cross-version check: the same endpoint from
> two different specification formats must produce the same record. That catches mistakes
> a single-format test cannot."

**"Why not just use Spectral / an existing scanner?"**
> "Spectral is S1, and it stays — it is the baseline, the source of the automatic labels,
> and an input feature. The model sits after it and ranks, following Flynn et al. 2018.
> RQ3 is whether that reduces the false positives an analyst has to read."

**"How long does the full corpus take?"**
> "I have not measured 2,529 yet — I will have that number for the methodology
> deliverable." *(Say this. Do not guess a figure in front of him.)*

**"What can it not do?"**
> "A specification can be secure on paper while the implementation is not. APIGUARD
> measures design-level risk. Experiment E4 on VAmPI and crAPI is what tests how far
> that carries." *(Saying the limit yourself is stronger than being asked twice.)*

---

## If something breaks live

- Nothing is compiled and nothing needs the network — the specs are already on disk.
- `demo\out\demo_output.txt` is the saved transcript of a good run. Open it and keep talking.
- Do not debug in front of him. Note it, move on, fix it after.
