# PHASES — fail-safe execution runbook

**The rule: every phase ends with a system we could submit.** No phase depends on a later
phase existing. If the clock kills us at a gate, we hand in what we have and it scores.

Challenges are published; the event starts ~14:00. Everything before that is Phase 0. Event
times are relative to the official 8-hour schedule (rulebook §5).

| Phase | Clock | Official slot | Ends with | If we stopped here |
|---|---|---|---|---|
| 0 | **before 14:00** | — | Engine + all 15 packs drilled + TC1 oracles verified | — |
| 1 | 0:20–0:40 | Problem selection | Theme confirmed, pack **regenerated at the event** | — |
| 2 | 0:40–1:25 | Swarm design | Roster, `visible_to`, prompts, guardrails tuned | — |
| 3 | 1:25–2:15 | Initial build | **Mandatory agents → CEO decision → trace** | ~55/100 ✅ |
| 4 | 2:15–3:10 | Initial build | **Full roster, constraint-grounded objection, ≥5 candidates** | ~80/100 ✅ |
| 5 | 3:10–3:55 | Initial build | **All 8 theme-required decision sections validated** | ~87/100 ✅ |
| 6 | 3:55–4:40 | Baseline testing | Golden run, degraded mode proven | ~90/100 ✅ |
| 7 | 4:55–5:55 | Adaptation | Surprise handled in whichever mode it arrives | ~96/100 ✅ |
| 8 | 5:55–6:25 | Submission | Package uploaded | — |
| 9 | 6:25–7:55 | Demos | Pitch delivered | — |

Score estimates are our own calibration, for triage only.

---

## Phase 0 — Before 14:00

### 0.1 Two integrity checks — do these first

**Check one: is this PDF public?**
Rulebook §1: *"Organizers, judges and anyone with prior access to confidential challenge
material may not compete."* If `Agent Swarm Test Cases.pdf` was distributed to all registered
teams, everything below is fair preparation. **If it reached us through a channel other teams
don't have, stop and tell the Rules Desk before building on it.** Confirm this before Phase 0
proceeds; it is not a detail.

**Check two: pre-build vs. event-build.**
Rulebook §4 permits *"reusable setup code, UI components, authentication boilerplate and
deployment templates"* but requires the *workflow, agent instructions, collaboration logic,
decision process, surprise-adaptation flow and challenge-specific outputs* to be created
during the event.

| Pre-build ✅ | Author at the event ❌ pre-built |
|---|---|
| `llm.py`, `state.py`, `cli.py`, plumbing | Agent mandates, prompts, guardrail text |
| `calculator.py` — AST sandbox, zero domain logic | The case pack actually submitted |
| `generate.py` — search, zero domain logic | `visible_to` tagging for the chosen theme |
| `scoring.py` normalization mechanics | Collaboration tuning, severity policy |
| Streamlit shell, README/slide templates | Every trace, decision, KPI, implementation plan |

**The packs are the sharp edge.** Resolve it this way: build all 15 packs in Phase 0 **as a
drill and as oracles**, but at the event **regenerate the chosen pack with `intake`** and
submit that one. Regeneration takes ~60 seconds, the artifact is genuinely produced during the
event, and the Phase 0 version becomes a correctness check rather than a deliverable.

**Ask the Rules Desk in writing in the first 10 minutes** whether a pre-built domain-agnostic
engine with event-authored prompts and event-generated packs is in scope. §1 makes a written
clarification binding. Asking costs nothing; guessing can cost everything. Then disclose every
pre-built file in the README's mandatory declaration section — disclosed reuse is permitted,
undisclosed reuse is what removes teams.

### 0.2 Build checklist

- [ ] `.venv` on Python 3.11 — **done**
- [ ] `requirements.txt` pinned: `pydantic`, `streamlit`, one LLM SDK
- [ ] **Two** model providers configured and tested end to end. Keys in `.env`, `.env` gitignored
- [ ] One local/offline model as ladder rung 3, in case venue wifi is hostile
- [ ] `llm.py` proven against forced 429, malformed JSON, total outage — all handled, none raise
- [ ] `calculator.py` self-check passes, **including hostile expressions**
      (`__import__('os')`, `().__class__`, circular metrics) — all must raise
- [ ] Pack validator rejects a deliberately broken pack with a readable error list
- [ ] Repo created, judge access verified from a logged-out browser, `TeamName_AgenticSwarm` agreed
- [ ] Everyone has run `python -m boardroom run` on their own machine once
- [ ] STRATEGY §8 file ownership agreed out loud

### 0.3 The drill — all 15 published cases

Lift each test case from the PDF into `briefs/<theme>_<tc>.txt`, verbatim. Then for every one:

```
intake → validate → full board run → (for TC2–TC5) surprise from its TC1 baseline
```

**Pass condition: 15 for 15, zero code edits between them.** Anything that forces a Python
change is a hole in the abstraction — fix it now, not at 15:00.

**Verify against the two hand-computed oracles in THEMES §3.3 and §5:**

| Oracle | Expect |
|---|---|
| Theme A TC1 | generator lands near `n_mfg 426 / n_sme 274 / n_retail 0 / rate 19%`, zero violations, net ≈ ₹1.48 cr. The greedy seed (450 mfg) must be flagged **infeasible on `concentration`** |
| Theme C TC1 | near `AI 2,500 / gaming 2,000 / edge ≈1,266`, ≈22,798 h used, margin ≈ ₹13.73 cr |

The oracles are hand-arithmetic and could be wrong. If the generator disagrees, **work out
which is right before assuming it's the code** — that reconciliation is itself the check.

Record per case: intake time, run time, whether the validator needed a repair retry.

Pay special attention to:
- **Theme A TC3 and TC4** — these change the lever space entirely and must go through
  **re-intake mode**, not delta mode. If re-intake doesn't work, adaptability is capped at ~4/10.
- **Theme B TC3/TC4** — the most qualitative packs. If they can't produce 3 computable
  metrics, the `signal:*` fallback (ARCHITECTURE §1) needs work before the event.

### 0.4 Timing budget to verify

```
intake + validate       < 60s
candidate generation    < 2s     (20k samples)
full board run          < 90s
surprise run            < 60s
switching themes        0 code changes
```

---

## Phase 1 — Confirm the theme (0:20–0:40)

Recommendation is already **Theme A — FINSWARM** (THEMES §2): fewest mandatory agents, richest
constraint set, and a disagreement that falls out of the arithmetic instead of being staged.
Use this slot to confirm nothing in the live pack differs from the PDF, not to re-open the debate.

```bash
python -m boardroom intake --brief briefs/themeA_tc1.txt --out cases/event.json
```

Then **read the generated pack aloud as a team** — two minutes, and it is not optional:
- Do the constraint expressions match the eight in the brief, exactly?
- Are the `assumption`-sourced variables genuinely absent from the brief? (All three themes
  say every needed fact is supplied — a long assumptions list means intake is inventing.)
- Does `diff cases/event.json` against the Phase 0 pack show only cosmetic differences?

**GATE 1 (0:40):** `event.json` validates, generator reproduces the Phase 0 oracle, every
constraint from the brief is present.

> **Abort rule:** intake unusable after one repair retry → hand-patch from the Phase 0 pack,
> and say so in the README. 10 minutes, and Phase 2 has the slack.

---

## Phase 2 — Roster and prompts (0:40–1:25)

The theme's mandated roster goes in; the generic one comes out.

- **C** — write the six Theme A mandates (Business Research, Finance & Treasury, Credit Risk,
  Marketing & Sales, Compliance & Customer Protection, CEO), inject the two guardrails into
  every prompt, and set the CEO objective text verbatim from the theme page.
- **B** — audit `visible_to` on every variable and `owner` on every constraint.
  **This is the highest-leverage 15 minutes of the event.** It decides whether agents genuinely
  specialise *and* which agents re-run on the surprise — two rubric categories at once. Credit
  Risk must own `default_cap` and `concentration`; Compliance must own `rate_cap`.
- **A** — wire the pack into `engine.py`, verify all five stages against a **stub LLM** first.
- **D** — README (§6 minimum contents) + architecture diagram. Neither needs working code.

**Insurance (~10 min if there's slack):** confirm a **Theme C** pack still runs cold. That's
the Q&A closer and the fallback if Theme A turns out badly.

**GATE 2 (hard, 1:25):** `python -m boardroom run --stub` completes all stages and writes
`runs/*.json`. Zero LLM calls. A plumbing bug found at hour 3 is unrecoverable — find it here.

---

## Phase 3 — Skeleton (1:25–2:15) → **first submittable build**

Real LLM. **Four agents only** (Research, Finance, Marketing, CEO — the rulebook's mandatory
set). Sequential, no objections yet. Generator and constraints already live.

**GATE 3:** one end-to-end real run produces a CEO decision, no crashes.

**Commit and tag.** From here we always have something to hand in.
Mandatory agents ✅ · visible I/O ✅ · trace ✅ · not hardcoded ✅. ~55/100.

> **Abort rule:** not green by **2:30** → drop Credit Risk and Compliance permanently and run
> on 4 agents. Four working agents beat six broken ones; the rulebook says so twice.
> (Cost: Theme A's best disagreement lives in Credit Risk vs Compliance, so this hurts — but a
> crashing board hurts more.)

---

## Phase 4 — Collaboration (2:15–3:10) → **the 20-point phase**

Highest-value hour. Guard it.

- Add **Credit Risk** and **Compliance & Customer Protection** (6 agents)
- Parallelize stage 1 with `ThreadPoolExecutor`
- Objections with `severity` and `cites_constraint`; one rebuttal turn on material/blocking;
  `outcome` recorded as revised/defended
- **Auto-blocking:** a violated constraint generates a blocking objection from its `owner`
- Comparison table: ≥5 candidates including the infeasible greedy seed with its named breach
- `MAX_ROUNDS = 3` wired and tested

**GATE 4:** the trace shows (a) the greedy seed rejected with `concentration` named, and
(b) at least one objection where an agent's recommendation **actually changed**
(`outcome == "revised"`).

> **If no genuine disagreement emerges:** in Theme A that means something is broken, because
> the arithmetic supplies one (THEMES §3.3). Check in order: `visible_to` too generous →
> everyone reasons identically; Compliance not seeing the segment mix; candidates too similar.
> **Never fabricate one** — §10 fabricated evidence.

~80/100.

---

## Phase 5 — Decision quality (3:10–3:55)

- `validate(Decision, pack)` enforcing the **theme's eight named sections** — customer segment,
  product terms, approval policy, budget allocation, risk limits, go-to-market, implementation
  sequence, measurable outcomes — plus ≥1 rejected alternative with reason, ≥3 KPIs with
  formula/baseline/target, and override justification
- One repair retry, then deterministic backfill with `confidence *= 0.8`

**GATE 5:** `validate()` returns `[]` on a fresh run.

~87/100. **Commit and tag.**

---

## Phase 6 — Baseline testing (3:55–4:40)

- [ ] Run 3×. Is the decision **stable**? Variance is a red flag under live verification;
      lower CEO temperature if so.
- [ ] `--fail credit_risk` → decision still produced, `degraded` populated, confidence dropped,
      warning visible. **Screenshot it.** Most-skipped rulebook requirement.
- [ ] **Golden run** → `runs/GOLDEN_baseline.json`. Verify `replay` **with wifi off**. Never overwrite.
- [ ] Export baseline evidence (§6): department outputs, debate trace, CEO decision
- [ ] Streamlit viewer up (D), read-only
- [ ] Trace sanity: can a stranger read the JSON and follow the argument?

**GATE 6:** offline replay works, degraded screenshot exists, evidence exported.
We are now safe; everything after is upside.

---

## Phase 7 — Surprise (4:55–5:55)

Surprise drops at 4:40. It will be one of TC2–TC5 for our theme. **Read for 10 minutes first.**

1. **Classify the mode.** Facts change but levers hold → **delta** (`--facts`). New lever
   space → **re-intake** (`--brief`). Theme A: TC2 and TC5 are delta, TC3 and TC4 are re-intake.
   Getting this wrong wastes 20 minutes; the classification is in THEMES §3.2.
2. Also patch **constraints** in delta mode — TC2 moves the default cap 5% → 5.5%, TC5 keeps
   it at 5.5% with cost of funds at 13%. A surprise that changes a *limit* and not just a
   *value* is the one most teams will miss.
3. Run it. Inspect. If the decision doesn't change, that may be **correct** — but the CEO must
   say *"the decision holds, and here is why the shock doesn't move it."* A justified unchanged
   decision scores; a silent one doesn't.
4. Confirm `invalidated_assumptions` is populated — TC5 asks for it **by name**.
5. Build the **diff view**: changed variables | invalidated assumptions | who re-ran | who
   didn't and why | baseline vs revised | KPI deltas.
6. Export surprise evidence. Save `runs/GOLDEN_surprise.json`.

**GATE 7:** revised decision with selective re-run, and we can name one agent that did *not*
re-run and explain why.

~96/100.

> **Abort rule:** impact derivation misfires → rerun everything and say so on stage:
> *"the changed variable wasn't in our visibility graph, so we re-opened the full board."*
> Honest degradation costs ~3 points; a broken surprise run costs 10.

---

## Phase 8 — Submission (5:55–6:25)

Assembly, not authoring — D has been building this since Phase 2.

- [ ] **Source** — repo link, judge access verified, `requirements.txt`, no secrets in history
- [ ] **README** — team + members, selected challenge, solution paragraph, agent table
      (role / input / output), install + run steps, models/frameworks/datasets, known
      limitations + failure handling, **pre-existing component declaration**
- [ ] **Architecture** — PNG/PDF: agents, inputs, shared state, communication, CEO path
- [ ] **Baseline evidence** — department outputs, debate trace, CEO decision
- [ ] **Surprise evidence** — changed input, revised trace, updated decision
- [ ] **Business summary** — max 2 pages: implementation steps, assumptions, risks, ≥3 KPIs
- [ ] **Pitch deck** — max 5 slides
- [ ] Named `TeamName_AgenticSwarm`

**Upload at 6:10, not 6:25.** Penalty is 5 points at +10 min, 15 at +30 — more than the entire
Presentation category. Upload early, replace if we improve. No penalty for uploading twice.

---

## Phase 9 — Demo (6:25–7:55)

See `PITCH.md`. Rehearse twice with a timer.

---

## Risk register

| # | Risk | Mitigation | Owner |
|---|---|---|---|
| R1 | PDF not public to all teams | **Verify before Phase 0 proceeds** (§0.1) | all |
| R2 | Rules Desk objects to the pre-built engine | Ask in writing in the first 10 min; full README disclosure; regenerate the pack at the event | all |
| R3 | Surprise is a lever-space change and re-intake is untested | Drill TC3/TC4 in Phase 0.3; classification table in THEMES §3.2 | B |
| R4 | Surprise changes a **constraint**, not a variable | `patch_constraints` in delta mode; TC2 and TC5 both do this | B |
| R5 | Generator misses the optimum | Verified against two hand-computed oracles; seeds always included | B |
| R6 | Guardrail breach (protected characteristics / overclaiming) | `guardrails` injected into every prompt + post-hoc check | C |
| R7 | Theme-required decision sections silently dropped | `required_decision_fields` validated in code | C |
| R8 | API quota dies mid-event | Two providers + local model + cached replay + golden run on disk | A |
| R9 | Agents all agree | Tighter `visible_to`, constraint-owner auto-objection. **Never fabricate.** | C |
| R10 | Streamlit eats 90 minutes | Phase 6, read-only, expendable. CLI is the system | D |
| R11 | Merge conflicts at hour 4 | Hard file ownership (STRATEGY §8); commit at every gate | all |
| R12 | Late submission | Upload at 6:10 | D |

---

## Gate summary

```
14:00 15-for-15 on the published cases, both oracles matched  → engine is ready
0:40  event.json regenerated, constraints verified            → decision model locked
1:25  stub run completes all stages                           → plumbing works
2:15  real 4-agent run → CEO decision                         → SUBMITTABLE
3:10  greedy seed rejected on a named constraint + a revision → collaboration scored
3:55  validate() returns [] incl. 8 theme sections            → decision quality scored
4:40  offline replay + degraded screenshot                    → safe
5:55  revised decision + selective re-run                     → adaptability scored
6:10  uploaded                                                → no penalty
```

Miss a gate → invoke that phase's abort rule. **Do not push into the next phase's time.**
