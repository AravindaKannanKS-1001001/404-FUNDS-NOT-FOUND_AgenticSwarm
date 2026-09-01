# Technical Report — The AI Boardroom

**Track:** Theme A — FINSWARM (FinNova Capital, digital small-business lending)

---

## 1. What the system is

A **domain-agnostic boardroom engine**. A business brief goes in; a validated decision
model comes out; a deterministic search finds the feasible optima; a roster of department
agents argues over them; a CEO agent issues a decision with a full audit trail.

The organising insight: **no Python file in this project knows what industry the problem
is.** The agent roster, the variables, the formulas, the hard constraints, the theme's
prohibitions and the theme's required decision sections all live in a JSON *case pack*.
Switching from FINSWARM (6 agents, lending) to CHIPSWARM (7 agents, GPU manufacturing) is
a different JSON file and **zero code changes** — both are in the repo and both run.

```
BRIEF --> INTAKE --> case_pack.json --> VALIDATOR --> SEARCH --> THE BOARD --> DECISION
          (tool,     roster, vars,      (proves it    (feasible  (roster from   (+ trace)
           not an    formulas,           computes)     optima)    the pack)
           agent)    CONSTRAINTS
```

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | — |
| Data contract | **Pydantic v2** | One typed schema shared by engine, agents, CLI and viewer; agent output is schema-validated on arrival |
| Arithmetic | **Python `ast` (stdlib)** | Sandboxed expression evaluator — see section 4 |
| Search | **stdlib `random` + local refinement** | No solver dependency; see section 5 |
| Concurrency | **`concurrent.futures.ThreadPoolExecutor`** | Stage-1 department analysis runs in parallel |
| LLM | **Gemini 3 Flash (preview)**, fallback Gemini 3.1 Flash Lite | Provider is pluggable; adapters for Gemini / Anthropic / OpenAI all present |
| UI | **Streamlit** (read-only) | A lens over the run JSON. The CLI is the system |
| Agent framework | **none** | Deliberate — see section 9 |

Total production code: **~1,480 non-blank, non-comment lines** across 13 modules.

---

## 3. How the agents were built

There is **no per-agent Python**. One function drives every department; the roster is data.

```json
{ "id": "credit_risk",
  "title": "Credit Risk Agent",
  "mandate": "Assess expected credit losses, portfolio default, segment concentration...",
  "signals": ["risk_score"] }
```

Each agent's prompt is assembled from four pack-driven pieces:

1. **Its mandate** — the role sentence above.
2. **Its fact slice.** Every variable carries `visible_to: [agent ids]`. `facts_for()`
   filters on it, so an agent is *structurally incapable* of reasoning about a variable it
   was not shown. Marketing cannot see `retail_default`; it therefore cannot drift into
   Credit Risk's job. Specialisation is enforced by the data model, not by asking politely.
   In the TC1 run, Credit Risk sees 10 of 22 variables.
3. **The constraints it owns.** `constraints[].owner` names one agent per hard limit.
   Credit Risk owns `default_cap` and `concentration`; Compliance owns `rate_cap`;
   Finance owns `liquidity`.
4. **The theme's guardrails**, injected verbatim into *every* prompt — for FINSWARM,
   "not personal financial advice" and "do not infer protected characteristics or
   recommend discriminatory lending."

Agents are explicitly forbidden to do arithmetic. They emit **lever preferences**
(`n_sme = 306`) and **0-1 signals** (`risk_score = 0.72`); every currency figure on screen
came from the sandbox.

### The five-stage protocol

| Stage | What happens |
|---|---|
| 0 - Generate | Deterministic candidate search — before any agent speaks |
| 1 - Analyse | Roster runs in parallel, each on its own fact slice, producing a `Recommendation` |
| 2 - Share | Recommendations digested into the shared state and trace |
| 3 - Challenge | Objections with `severity`; a violated constraint **auto-generates** a blocking objection from its owner; targeted agents get one rebuttal turn (`revised` / `defended`) |
| 4 - Compare | Weighted scoring across the cohort; anything infeasible scores 0 |
| 5 - Decide | CEO produces a `Decision`, validated **in code**, one repair retry, then deterministic backfill |

Debate is capped at 3 rounds and terminates when no material objection is unresolved.

---

## 4. Formulas from the LLM, arithmetic from a sandbox

The case pack stores metrics as **expression strings**:

```json
"portfolio_default_pct": "credit_loss / max(deployed, 1)",
"max_segment_share": "max(n_retail*retail_loan, n_sme*sme_loan, n_mfg*mfg_loan) / max(deployed, 1)"
```

Because an LLM may author these, they are treated as semi-untrusted. `calculator.py`
whitelists the AST node types and never evaluates raw text:

- no attribute access, subscripting, comprehensions, imports, or `__builtins__`
- calls restricted to `min max abs round exp sqrt log`
- unknown names rejected **before** compilation
- compiled expressions are `lru_cache`d (the search evaluates ~20 expressions 20k times)

Hostile inputs such as `__import__('os')` and `().__class__` are in the module's own
self-check and must raise. This is what lets us answer *"how was that number generated?"*
by pointing at a formula, and *"you let an LLM write executable expressions?"* by pointing
at the whitelist.

---

## 5. Constraints are checked, not weighted

Hard limits live in the pack with a label and an owning agent:

```json
{ "id": "concentration",
  "expr": "max_segment_share <= concentration_limit",
  "label": "No segment may receive more than 70% of deployed capital",
  "owner": "credit_risk" }
```

A violation makes a strategy **infeasible — score 0** — not merely low-ranked, and it
becomes a *business argument* with a named speaker.

This matters because in TC1 **the profit-maximising portfolio is arithmetically illegal**.
The naive greedy answer (450 manufacturers + 250 SMEs, the two best margins) asks to lend
INR 55.5 crore against INR 30 crore of capital and puts manufacturers at ~73% of the book.
It breaches `liquidity` *and* `concentration`, and Finance and Credit Risk each blocked it
in the live run.

### Candidate generation

`generate.py` samples 8k bounded lever vectors, discards anything infeasible, then refines
the best with compass search plus a stochastic polish (random sampling alone finds the
basin but not the constrained vertex). It lands within ~1% of the hand-computed LP optimum
in under 2 seconds with **no solver dependency**.

The search ranks on the deterministic objective only. Agent signals arrive *afterwards* and
can reorder the list. That gap is the point:

> **The search finds what is feasible. The board decides what is wise.**

The organisers' own brief says *"do not approve a strategy solely because it maximizes
short-term revenue"* — the optimum is explicitly not the answer.

---

## 6. Decision quality is enforced in code

FINSWARM mandates eight named sections. `validate(decision, pack)` checks every one, plus
at least one rejected alternative with a reason, at least three KPIs with
formula/baseline/target, an implementation sequence with owning functions, cited evidence,
trade-offs, and a written justification if the CEO overrides the ranking. Failure triggers
one repair retry with the error list appended; a second failure triggers deterministic
backfill and a confidence penalty. **A CEO output missing a mandated section never reaches
a judge.**

---

## 7. Adaptation: only what the news invalidated

`visible_to` does double duty — it is both the fact filter *and* the impact map. On a
surprise, changed variables map through `visible_to` to exactly the agents that must
re-run; everyone else keeps their position, recorded with a stated reason.

Two modes:

- **delta** (`--facts`) — variables move, pack structure holds. TC2 and TC5.
- **re-intake** (`--brief`) — a whole new lever space. TC3 and TC4 change what the decision
  variables *are* (marketing channels, reviewer headcount), so they are re-modelled rather
  than perturbed.

Constraint *limits* are themselves pack variables (`default_limit`, `concentration_limit`),
so a surprise that tightens a **limit** rather than a value — which TC2 does, 5% to 5.5% —
is the same one-line delta, not string surgery on the constraint expressions.

`invalidated_assumptions` is populated as a first-class field because TC5 asks for it by
name: *"identify which original assumptions are no longer valid."*

---

## 8. Reliability

A five-rung ladder per LLM call, which **never raises**:

```
primary model -> retry once -> secondary model -> last-good cached output -> neutral stub
```

The last rung records the agent in `state.degraded` and multiplies final confidence by
0.8 per degraded agent. `--fail credit_risk` kills an agent on purpose to demonstrate this.
An invalid API key was used during development and every one of the six agents degraded
cleanly: the board still produced a validated decision, at confidence 0.00, with the
degradation flagged on the output.

Every run writes `runs/<ts>.json`; `python -m boardroom replay <file>` renders the whole
board with **zero network calls**.

Verification: `python -m boardroom.selfcheck` runs 10 module self-checks plus an end-to-end
baseline/surprise/replay pass. `python -m boardroom.drill` runs every case pack through the
full board and checks the results against hand-computed optima. Both pass offline.

---

## 9. What we deliberately did not build

| Cut | Reason |
|---|---|
| LangGraph / CrewAI / AutoGen | Five sequential stages with one parallel fan-out is a `ThreadPoolExecutor` and a for-loop. A framework adds install risk and API churn for no functional gain |
| An LP/MIP solver (`scipy`, `pulp`) | Bounded random search plus local refinement lands within ~1% on every published case, in under 2s, with zero dependencies |
| A hand-written impact map | Derived from `visible_to`, so it cannot drift out of sync with the fact filter |
| A real frontend | Streamlit reads the same JSON the CLI writes |
| Vector DB / RAG | The case pack fits in a prompt |
| A 7th/8th agent | Two more failure modes and two fewer demo minutes; agent count is not a score |

---

## 10. Repository layout

```
boardroom/
  state.py        Pydantic contract - the shared state and append-only trace
  calculator.py   AST sandbox: safe_eval / compute / check
  generate.py     bounded search + compass + stochastic refinement
  scoring.py      weighted score over role-mapped metrics
  llm.py          fallback ladder, JSON repair, offline stub, 3 provider adapters
  agents.py       roster-driven prompt rendering; visible_to fact filtering
  engine.py       the 5-stage protocol, adapt(), degraded mode
  intake.py       brief -> pack + deterministic pack validator
  cli.py          run | surprise | replay | intake
  viewer.py       Streamlit lens over runs/*.json
  oracles.py      hand-computed optima the search is checked against
  selfcheck.py    every module's self-check + end-to-end
  drill.py        every case pack through the full board
prompts/          _department.md  _ceo.md  _challenge.md  _intake.md
cases/            themeA_tc1.json  themeC_tc1.json
briefs/           raw test-case text + surprise deltas
```

### Running it

```bash
pip install -r requirements.txt
python -m boardroom.selfcheck                          # offline, no API key needed
python -m boardroom run --case cases/themeA_tc1.json
python -m boardroom surprise --run runs/<f>.json --facts briefs/themeA_tc2.facts.json
python -m boardroom replay runs/<f>.json               # offline
python -m boardroom run --case cases/themeA_tc1.json --fail credit_risk
streamlit run boardroom/viewer.py
```

With no API key the whole system runs on a deterministic stub — structure, search,
constraints and validation are all exercised without a network.

---

## 11. Disclosures

- **AI coding assistance** was used during development, as permitted by the rulebook.
  Architecture decisions, the case-pack modelling, the constraint sets and the
  hand-computed optima were authored and verified by the team.
- **Models used at runtime:** Gemini 3 Flash (preview) primary, Gemini 3.1 Flash Lite
  fallback, via `google-generativeai`.
- **Dependencies:** `pydantic`, `streamlit`, `google-generativeai`, with optional `openai`
  and `anthropic` adapters. Everything else is Python standard library.
- **Data:** all figures are the organisers' synthetic test-case data. No external or
  personal data is used. No secrets are committed; API keys are read from the environment
  or a gitignored `.env`.
- **Reused / pre-existing components:** none beyond the pinned third-party libraries above.
- **Known limitations:** candidate search is stochastic (seeded, so runs are reproducible)
  and lands within ~1% of the true optimum rather than exactly on it; the intake path
  requires a live LLM provider; agent prose varies run to run while the deterministic
  numbers, constraints and rankings do not.
