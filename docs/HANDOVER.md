# HANDOVER — implementation brief

For the session that builds this. Read this file, then `THEMES.md`, then `ARCHITECTURE.md`.
`STRATEGY.md` and `PITCH.md` are context, not build input — skim once, don't implement from them.

> **Steps 1–12 built and green (2026-09-01).** `python -m boardroom.selfcheck` and
> `python -m boardroom.drill` both pass offline. See README "Status" for what remains
> (real-`intake` drill, prose quality, golden run, slides — all need a provider key / the event).
> Deviations from this doc, all noted inline below: constraint limits are pack *variables*
> not string literals; the TC1 oracle was corrected (`0/315/90`, not `426/274`); `generate`
> gained compass + stochastic local search to reach the LP vertex; an OpenAI adapter and a
> `_detect_kind()` were added to `llm.py`; `Decision` gained a `chosen` field.

---

## 0. What you are building

A domain-agnostic "AI boardroom" for the Agentic Swarm hackathon. A raw business brief goes in;
a validated decision model comes out; a bounded search finds feasible optima; a roster of
department agents argues over them; a CEO agent issues a decision with an audit trail.

**The single invariant: no Python file is domain-specific.** Roster, variables, formulas,
constraints, guardrails and required decision sections all live in `case_pack.json`. If you
find yourself writing `if theme == "FINSWARM"`, stop — it belongs in the pack.

Working dir: `A:\NOTES_SEM#\notes generator\Agent Swarym`
Venv: `.venv` (Python 3.11.9) already exists. `.venv\Scripts\python`.
Source material: `Agent Swarm Test Cases.pdf`, `Agentic_Swarm_Official_Rulebook (1).docx`.

---

## 1. How to work

- **Build in the order in §3.** It is dependency-ordered and — deliberately — the entire
  deterministic core is testable **before any API key is needed**. Do not jump to the LLM parts.
- **Every step has an acceptance check. Run it before moving on.** If a check fails, fix it
  there; do not carry a broken layer forward.
- **Tests are `assert`-based `demo()` under `if __name__ == "__main__"`.** No pytest, no
  fixtures, no framework. One runnable check per non-trivial module.
- **Dependencies: `pydantic`, `streamlit`, one LLM SDK. Nothing else.** No scipy, no pulp, no
  langgraph, no crewai, no instructor. If something seems to need a new dep, it doesn't — check
  `STRATEGY.md §7` for why it was cut.
- Keep it around 800 lines total. If a module is ballooning, it's doing someone else's job.
- Commit after each acceptance check passes.

---

## 2. File manifest

```
boardroom/
  __init__.py
  state.py        Pydantic models — the shared contract          (ARCHITECTURE §6)
  calculator.py   AST sandbox: safe_eval, compute, check         (ARCHITECTURE §3)
  generate.py     bounded lever search -> feasible candidates    (ARCHITECTURE §4)
  scoring.py      weighted score over role-mapped metrics        (ARCHITECTURE §5)
  llm.py          call() with retry + model fallback + JSON repair + stub mode
  agents.py       roster-driven; facts_for(); one department fn  (ARCHITECTURE §7)
  intake.py       brief -> pack -> validate                      (ARCHITECTURE §2)
  engine.py       5-stage protocol, adapt(), degraded mode       (ARCHITECTURE §8, §9)
  cli.py          intake | run | surprise | replay               (ARCHITECTURE §11)
  viewer.py       streamlit, read-only over runs/*.json
prompts/
  _department.md  _ceo.md  _intake.md
briefs/
  themeA_tc1.txt … themeC_tc5.txt      15 files, verbatim from the PDF
cases/
  themeA_tc1.json … (generated)
runs/
  (generated)
requirements.txt
```

---

## 3. Build order with acceptance checks

### Step 1 — `state.py`
Copy the models from `ARCHITECTURE §6` as written. Add `run_id` generation (`uuid4().hex[:8]`)
and a `trace(state, agent, kind, **payload)` helper that appends a `TraceEvent`.

**Accept:** `BoardroomState(...).model_dump_json()` round-trips.

---

### Step 2 — `calculator.py` ← *the foundation, get it exactly right*
`safe_eval`, `compute`, `check` from `ARCHITECTURE §3`, verbatim. Node whitelist, `FUNCS` map,
no `__builtins__`.

**Accept — `demo()` must assert all of:**
- `safe_eval("__import__('os')", {})` raises
- `safe_eval("().__class__", {})` raises
- `safe_eval("x.attr", {"x": 1})` raises
- `compute({"a": "b + 1", "b": "a + 1"}, {})` raises (circular)
- `compute({"a": "1/max(x,1)"}, {"x": 0})` == `{"a": 1.0}` (guarded division)
- a metric referencing an earlier metric resolves across passes

---

### Step 3 — Theme A TC1 pack, **by hand**, and the oracle ← *no LLM yet*
Write `cases/themeA_tc1.json` manually from `THEMES.md §3.1` and the schema in
`ARCHITECTURE §1`. This validates the calculator and the schema together, and it becomes the
oracle everything else is checked against.

**Unit discipline — this is the classic bug.** Work in plain INR throughout.
`1 lakh = 100_000`, `1 crore = 10_000_000`. So capital = `300_000_000`, retail avg loan =
`400_000`, liquidity reserve = `30_000_000`, acquisition budget after setup = `4_200_000`.

**Accept:** `python -m boardroom.oracles` passes. It asserts (no LLM involved):
- feasible optimum `n_retail 0 / n_sme 315 / n_mfg 90 @ 0.19` → zero violations,
  `net_income` in `[₹6.4M, ₹6.8M]`
- greedy seed `n_mfg 450 / n_sme 250` → violates **both** `liquidity` and `concentration`

**DONE (2026-09-01).** The original oracle here (`426/274`, ≈₹1.48cr) was wrong — it ignored
that ₹30cr capital only funds ~₹27cr of loans after the reserve. Reconciled by hand; corrected
figures are in `THEMES.md §3.3` and `boardroom/oracles.py`. Limits are pack *variables*
(`default_limit`, `rate_limit`, `concentration_limit`), not literals in the constraint
strings — makes TC2/TC5 delta-mode a variable patch, not string surgery.

---

### Step 4 — `generate.py`
Bounded random search from `ARCHITECTURE §4`. Respect `min`/`max`/`step` per lever. Filter by
`check()`. Rank on `pack["objective"]`. `diversify()` greedily skips candidates within ~5%
normalized lever distance. **Always append `seed_strategies`, even when infeasible** — the
rejected alternative must be a real one with a named breach.

**Accept:** on Theme A TC1, 20k samples in <2s, top candidate within 3% of the ₹6.59M oracle
(`boardroom.oracles.verify`), `n_retail` near 0, and both seed corner strategies present in the
output carrying their violations.

---

### Step 5 — `scoring.py`
Five fixed weight slots; `score_inputs` maps each to `metric:<name>` or `signal:<name>`.
`normalize` min-maxes across the cohort and inverts when `direction == "min"`.
**Any strategy with violations scores 0.**

**Accept:** feeding synthetic signals reorders the ranking away from the pure-objective order —
i.e. the board can overrule the search.

---

### Step 6 — `llm.py`
One `call(system, user, schema) -> dict`. Ladder: primary → retry once → secondary model →
last-good cache → `{"status": "unavailable"}`. **Never raises.** JSON parse failure → one repair
retry with the error appended. Add `--stub` mode returning canned JSON so the engine is testable
offline.

**Accept:** simulate 429, malformed JSON, and total outage — none raise, each returns something
usable, and the outage path records into `degraded`.

---

### Step 7 — `agents.py` + `prompts/_department.md`, `_ceo.md`
Two templates only. Role text comes from `pack["roster"]`. `facts_for()` filters on
`visible_to`. Inject `pack["guardrails"]` into **every** prompt. Agents are forbidden to write
currency figures; they emit `lever_view` and 0–1 `signals`.

**Accept:** rendering the Credit Risk prompt shows only its `visible_to` variables, both Theme A
guardrails, and the constraints where `owner == "credit_risk"`.

---

### Step 8 — `engine.py`, stub mode first
Stages 0–5 from `ARCHITECTURE §8`. `MAX_ROUNDS = 3`, hard exit. A violated constraint
auto-generates a blocking objection from its `owner`. `validate(Decision, pack)` enforces
`required_decision_fields` plus ≥1 rejected alternative, ≥3 KPIs, implementation, evidence,
trade-offs, override justification — one repair retry, then deterministic backfill with
`confidence *= 0.8`.

**Accept:** `python -m boardroom run --case cases/themeA_tc1.json --stub` completes all stages
and writes `runs/*.json` with **zero LLM calls**. Then the same without `--stub` produces a real
decision where `validate()` returns `[]`.

---

### Step 9 — `intake.py` + `prompts/_intake.md`
Brief → pack → deterministic validator (full checklist in `ARCHITECTURE §2`).
Prompt rule: **extraction, not inference** — all three themes state every needed fact is
supplied. Prefer emitting `source: "assumption"` with a note, or omitting a metric, over
inventing a number.

**Accept:** `intake` on `briefs/themeA_tc1.txt` produces a pack that passes the validator **and**
reproduces the Step 3 oracle. A deliberately broken pack yields a readable error list.

---

### Step 10 — `adapt()` in `engine.py`
Both modes from `ARCHITECTURE §9`. Delta (`--facts`) must also `patch_constraints` — Theme A
TC2 and TC5 move the default cap, not just values. Re-intake (`--brief`) diffs packs. Derive
affected agents from `visible_to` ∪ newly-violated constraint owners. Populate
`unchanged` (with reasons) and `invalidated_assumptions` — **TC5 asks for the latter by name**.

**Accept:** TC2 as delta re-runs Credit Risk/Finance/Research and skips at least one agent with
a stated reason; TC3 as re-intake produces a new lever space and still yields a valid decision.

---

### Step 11 — `cli.py`, then `viewer.py`
CLI per `ARCHITECTURE §11`, including `--fail <agent_id>`. Streamlit is **read-only over
`runs/*.json`** with a weights sidebar for the "change one input" demo. Build it last; it is
expendable.

**Accept:** `replay` renders a saved run with networking disabled.
`run --fail credit_risk` still produces a decision, with `degraded` populated and confidence dropped.

---

### Step 12 — the drill
Transcribe all 15 test cases into `briefs/`, then run intake → board → surprise on each.
**Target: 15 for 15 with zero code edits.** Verify the Theme C TC1 oracle from `THEMES.md §5`
(AI 2,500 / gaming 2,000 / edge ≈1,266, ≈22,798 h, ≈₹13.73 cr).

Anything that forces a Python change is a hole in the abstraction — fix the abstraction.

---

## 4. Do not

- Add a dependency. Especially not an LP solver or an agent framework.
- Hardcode a roster, a theme name, or a metric name in Python.
- Let an LLM compute a number. Agents emit levers; the sandbox computes.
- Fabricate a disagreement. The objection *field* is required; a *fake* objection is rulebook
  §10 fabricated evidence. In Theme A the arithmetic supplies a real one.
- Build a real frontend. Polish scores zero.
- Skip the `demo()` self-checks. They are the only tests this project gets.

---

## 5. Decisions that are not yours to make

Flag these to the user rather than deciding:

1. **Is the test-case PDF public to all teams?** Rulebook §1 bars anyone with prior access to
   confidential challenge material. Unresolved — see `PHASES.md §0.1`.
2. **Pre-build vs. event-build scope.** Engine and sandbox are reusable setup code; prompts,
   packs and traces must be authored at the event. The plan says build the packs now as oracles
   but regenerate the submitted one with `intake` on the day. Rules Desk confirms this in the
   first 10 minutes.
3. **Theme choice.** Plan recommends A — FINSWARM. Confirmed at 0:20–0:40, not by you.
4. **Model/provider selection** and where keys live.

---

## 6. First commands

```bash
cd "A:/NOTES_SEM#/notes generator/Agent Swarym"
.venv/Scripts/python -m pip install pydantic streamlit
.venv/Scripts/python -m pip freeze > requirements.txt
mkdir -p boardroom prompts briefs cases runs
```

Then Step 1. Stop at each acceptance check and report the result before continuing.

**Step 3 is the one that matters most** — a hand-written pack whose greedy portfolio is proven
illegal, with no LLM in the loop. Everything downstream is plumbing around that fact.
