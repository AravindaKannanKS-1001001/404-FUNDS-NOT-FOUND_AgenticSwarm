# STRATEGY — what we build and why

Read `THEMES.md` first if you haven't. It contains the published test cases and the four
findings that reshaped this plan.

## 1. What we now know, and what it forces

The organizers published **three themes × five test cases = fifteen scenarios**, in advance.
TC1 is a baseline, TC2–TC4 are surprises, **TC5 is a live test** in every theme.

Three hard consequences:

| Fact | Forces |
|---|---|
| Each theme mandates a **different agent roster** (6 / 7 / 7), none matching a generic one | Roster is **case-pack data**, not a Python constant. Chief of Staff demotes to a disclosed pre-board tool to stay under the 8-cap. |
| TC1s are **constrained optimization problems** with judge-checkable optima | A **constraints block** and a **candidate generator**. Letting an LLM pick three round numbers loses Business Value outright. |
| TC3/TC4 change the **lever space**, not just the facts; TC5 runs **live** | Surprise needs a **re-intake mode** alongside delta mode, and both must be fast. |

Everything domain-specific — roster, variables, formulas, constraints, guardrails, required
decision sections — lives in `case_pack.json`. **No Python file knows what industry this is.**

---

## 2. Positioning — the important reframe

Two hours ago the pitch was "works on any unseen business problem." **That claim is now
weaker and we should drop it.** The organizers handed us all fifteen scenarios; generality on
unseen problems isn't the differentiator it was.

Replace it with a claim that is smaller, checkable, and far stronger in the room:

> **"It runs all fifteen of your published test cases without a code change. Pick the theme we
> didn't prepare — we'll run it cold."**

Every other team will build for their theme's TC1 and bolt the surprise on. Handing a judge
the theme we *didn't* pick and producing a full board decision from a cold start is the most
convincing thing available to us in a 2-minute Q&A, and the Phase 0 drill already produces it.

The second claim, unchanged and still honest:

> "The search finds what is **feasible**. The board decides what is **wise**."

We are not claiming a new optimization algorithm. We're claiming a decision process that
sits on top of one, leaves an audit trail, and weighs the things a solver structurally
cannot see.

---

## 3. The four bets

### 3.1 Hard constraints, evaluated deterministically

The pack carries constraint expressions (`portfolio_default_pct <= 0.05`) with a label and an
**owning agent**. The sandbox evaluates them. A violation makes a strategy *infeasible* —
score 0 — not merely low-ranked.

This is the highest-value addition from the PDF, because in Theme A TC1 **the profit-maximizing
portfolio is arithmetically infeasible**: 450 manufacturers breaches the 70% concentration cap
(THEMES §3.3). We catch that with a formula, not an opinion. Then `constraints[].owner` turns
the violation into a *business argument* — Credit Risk speaks for the concentration cap, and
its blocking objection is grounded in arithmetic a judge can verify.

Most teams will present the greedy answer and not notice.

### 3.2 Candidate generation, then a board that can overrule it

20,000 bounded random lever samples → filter by constraints → top-K diverse feasible optima,
plus the seed corner strategies (**included even when infeasible**, so the rejected
alternative is a real one with a named breach). ~35 lines, no solver dependency.

Ranking at generation time uses the deterministic objective only. Agent signals — brand risk,
compliance health, customer impact — arrive later and can reorder the list. That gap *is* the
product:

> Theme C TC1 says *"Strategic note: two long-term industrial customers."* No formula contains
> that. Theme A says *"do not approve a strategy solely because it maximizes short-term
> revenue."* The organizers are telling us the optimum is not the answer.

### 3.3 Formulas from the LLM, arithmetic from a sandbox

The LLM writes `"net_income": "interest_income - credit_loss - funding_cost - ..."`. It never
computes. A ~70-line stdlib AST evaluator with a node whitelist runs it.

- **Survives live verification.** *"How was that number generated?"* → open the expression,
  point at the variable keys. Teams whose LLM invented "₹1.48 crore" fail this on stage.
- **Survives the security question.** *"You let an LLM write executable expressions?"* →
  whitelisted nodes, no `__builtins__`, no attribute access, no imports, unknown names
  rejected pre-compile. Hostile inputs are in the self-check.

### 3.4 `visible_to` does double duty

Every variable carries the list of agents allowed to see it. That one field is:

- **the fact filter** — Marketing literally cannot see `retail_default`, so specialisation is
  structural rather than a label on a prompt; and
- **the impact map** — on a surprise, changed variables → `visible_to` → exactly which agents
  re-run.

The demo's best moment is the agents that *don't* re-run. Every other team re-runs everything.

---

## 4. The board

**The roster comes from the pack.** Recommended theme is **A — FINSWARM** (THEMES §2):

| Agent | Owns | Its job in the drama |
|---|---|---|
| Business Research | Market, demand, competitors, segments | Sets the demand ceiling everyone builds on |
| Finance & Treasury | Cost of funds, servicing, liquidity, net income | Backs the highest-value feasible portfolio |
| **Credit Risk** | Expected losses, concentration, portfolio quality | **Owns the default and concentration caps — the veto** |
| Marketing & Sales | Segments, channels, acquisition budget | **Fights the exclusion of retail** — 1,500 demand untouched |
| **Compliance & Customer Protection** | Fair treatment, affordability, conduct | **Objects to serving zero small shops** |
| CEO | Reconcile, decide, plan | Selects, rejects, explains, sequences |

Six judged agents. **Chief of Staff intake sits outside the count** as a disclosed pre-board
tool (rulebook §2 exempts deterministic tooling); if a judge counts it we're at 7, still legal.
Themes B and C mandate 7, which is exactly why intake must not consume a slot.

We don't manufacture a disagreement here. Theme A's arithmetic produces one: the feasible
optimum serves **zero retail shops**, Marketing and Compliance both have legitimate grounds to
object, Credit Risk has legitimate grounds to defend, and the brief explicitly instructs the
CEO not to just take the money. We referee.

---

## 5. Rubric map

| Criterion | Pts | Mechanism | Phase |
|---|---:|---|---|
| **Business value** | 25 | Judge-verifiable optima; hard constraints checked not weighted; theme's own 8 required decision sections; KPIs with formula + baseline + target | 1, 5 |
| **Agent specialisation** | 15 | Roster from the pack; `visible_to` fact slices; `constraints[].owner` gives each agent something only it can veto | 3, 4 |
| **Collaboration** | 20 | Shared state; objections with `severity` + `cites_constraint`; forced rebuttal; ≥5 candidates compared incl. an infeasible seed; append-only trace | 4 |
| **Decision quality** | 15 | `validate()` enforces the **theme-specific** required sections + ≥1 rejected alternative + ≥3 KPIs + override justification | 5 |
| **Adaptability** | 10 | Delta **and** re-intake modes; derived impact map; `invalidated_assumptions` (TC5 asks for it by name) | 7 |
| **Technical** | 10 | End-to-end CLI, AST sandbox with hostile-input tests, fallback ladder, `--fail`, offline replay | 3, 6 |
| **Presentation** | 5 | Trace view, 8-min script, **cold-run closer on an unprepared theme** | 9 |

Tie-break order is Business Value → Collaboration → Adaptability. Weight effort the same way.
**Frontend polish earns zero** — the rulebook says so twice.

---

## 6. Claims discipline

Rulebook §10 forbids fabricated traces, screenshots and metrics. §4 requires assumptions to be
labelled rather than presented as supplied facts. On top of that, **each theme carries its own
prohibitions** and they are deliberate traps:

| Theme | Guardrail | Failure mode |
|---|---|---|
| A | No inferring protected characteristics; no discriminatory lending; not personal financial advice | An agent segmenting by anything protected |
| B | No claiming unavailable integrations, certifications, security controls or AI accuracy; separate confirmed from roadmap | An agent saying "we're SOC 2 compliant" |
| C | Don't invent semiconductor specifications; all values are synthetic planning data | An agent citing a real process node |

These go in a `guardrails` block injected into **every** prompt, plus a post-hoc check.
Cheap to add, and exactly the kind of thing judges probe on purpose.

External figures (the Afresh / Wasteless numbers from the group chat) stay off every slide
unless someone opens the source. We don't need them — we have judge-verifiable arithmetic.

---

## 7. What we are deliberately not building

| Cut | Why | Add back when |
|---|---|---|
| Per-domain `calculator.py` | Three rosters, fifteen packs. Replaced by formulas-in-JSON + AST sandbox. | Never |
| An LP/MIP solver (`scipy`, `pulp`) | 20k random samples over ≤6 levers lands within a percent on all three TC1s, in under a second, with no dependency. | Only if a pack appears with a nasty integer space |
| Hand-written `IMPACT` map | Derived from `visible_to`. | Never |
| LangGraph / CrewAI / AutoGen | *No bonus for framework choice.* Five stages and one parallel fan-out is a `ThreadPoolExecutor` and a for-loop. | Never |
| Real frontend | Streamlit reads the same JSON the CLI writes. Polish scores zero. | Never |
| Vector DB / RAG | Nothing in the rubric rewards retrieval; the pack fits in a prompt. | Never |
| 1000-scenario benchmark during the event | 60 minutes we don't have. | Phase 8 only |
| A 7th/8th judged agent | Two more failure modes, two fewer demo minutes, zero points | Never |

---

## 8. Roles for 3–4 people

Everyone editing `engine.py` at hour 3 is how hackathons die. Hard file ownership:

| Person | Owns | Never touches |
|---|---|---|
| **A — Engine** | `state.py`, `engine.py`, `llm.py`, fallback ladder, trace writer | prompts, packs |
| **B — Math** | `calculator.py`, `generate.py`, `scoring.py`, pack validator, **all 15 packs**, the TC1 oracles | engine internals |
| **C — Agents** | `prompts/_department.md`, `_ceo.md`, roster mandates, guardrail injection, decision validator | engine, calculator |
| **D — Evidence** | Streamlit viewer, README, architecture diagram, 5 slides, baseline/surprise exports, **submission upload** | everything else |

Three people: D's work splits across A and C after their gates; the viewer is first to be cut.

The submission package has a real deadline and a 5-points-per-10-minutes penalty.
**Someone owns it from hour 0, not hour 7.**
