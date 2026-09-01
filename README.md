# The AI Boardroom — Agentic Swarm submission

**Team: 404 : FUNDS NOT FOUND** — Aravinda Kannan KS (lead, 24BCE1290) · Tarun Krishna Manivannan (24BCE5460) · Krishna Prasad M (24BCE5519) · Eluke. Srinitha (24BCE1639)

**Track: Theme A — FINSWARM** (FinNova Capital, digital small-business lending)

> Most teams build a swarm for *their* problem. We built a **board that convenes on any
> problem** — hand it a brief, it constructs the decision model, and six executives argue it
> out with a full audit trail.

**No Python file in this repository knows what industry the problem is.** The agent roster,
the variables, the formulas, the hard constraints, the theme's guardrails and the theme's
required decision sections all live in a JSON *case pack*. Switching from FINSWARM (6 agents,
lending) to CHIPSWARM (7 agents, GPU manufacturing) is a different JSON file and **zero code
changes** — both packs are in `cases/` and both run.

```
BRIEF --> INTAKE --> case_pack.json --> VALIDATOR --> SEARCH --> THE BOARD --> DECISION
          (tool,     roster, vars,      (proves it    (feasible  (roster from   (+ trace)
           not an    formulas,           computes)     optima)    the pack)
           agent)    CONSTRAINTS
```

---

## The agents

| Agent | Owns | Hard constraint it can veto |
|---|---|---|
| Business Research | Market, demand, competitors, segments | demand caps |
| Finance & Treasury | Cost of funds, servicing, liquidity, net income | `liquidity` |
| Credit Risk | Expected losses, concentration, portfolio quality | `default_cap`, `concentration` |
| Marketing & Sales | Segments, channels, acquisition budget | `acq_cap` |
| Compliance & Customer Protection | Fair treatment, affordability, conduct | `rate_cap` |
| CEO | Reconcile, decide, plan | — |

**Intake** turns a raw brief into a validated case pack. It is a deterministic pre-board
tool, not a judged agent.

---

## Quick start

```bash
pip install -r requirements.txt

# Runs fully offline on a deterministic stub — no API key needed
python -m boardroom.selfcheck        # 10 module self-checks + end-to-end
python -m boardroom.drill            # every case pack through the full board

# With a provider key (GOOGLE_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY)
python -m boardroom run      --case cases/themeA_tc1.json
python -m boardroom surprise --run runs/<f>.json --facts briefs/themeA_tc2.facts.json
python -m boardroom replay   runs/<f>.json                    # offline, zero network
python -m boardroom run      --case cases/themeA_tc1.json --fail credit_risk
streamlit run boardroom/viewer.py
```

Recorded evidence from live runs is in `evidence/` and can be replayed with no network:

```bash
python -m boardroom replay evidence/baseline_TC1.json
python -m boardroom replay evidence/surprise_TC2.json
```

---

## Results on the published test cases

### TC1 baseline — the profit-maximising portfolio is arithmetically illegal

The naive greedy answer (450 manufacturers + 250 SMEs, the two best margins) asks to lend
**INR 55.5 crore against INR 30 crore of capital** and puts manufacturers at ~73% of the book
against a 70% cap. Finance blocked it on `liquidity`, Credit Risk on `concentration`.

The feasible optimum (`G1`: 0 retail / 306 SME / 96 manufacturer loans at 19%) serves **zero
retail shops** — the largest demand pool and the smallest businesses. Marketing backed a
retail-inclusive alternative and filed a *material* objection; Compliance counter-objected
that higher retail exposure raises conduct risk. A real, unscripted cross-functional
disagreement, forced by the numbers.

Full transcript: [`submission/TC1_baseline.md`](submission/TC1_baseline.md)

### TC2 surprise — the pilot is infeasible as designed

Defaults jump to 8% / 5% / 7% and the risk committee tightens the portfolio cap to 5.5%.
Compliance, Credit Risk and Finance re-ran; **Research and Marketing did not**, because the
changed variables are not visible to them.

The search returned **zero feasible portfolios**. The 70% concentration cap forces at least
30% of the book into a segment defaulting at 7% or worse, breaching the 5.5% cap; an all-SME
book clears the default cap but breaches concentration. The two rules are jointly
unsatisfiable — arithmetic, not opinion. That is precisely what TC2 asks: *continue, redesign
or pause?*

Full transcript: [`submission/TC2_surprise.md`](submission/TC2_surprise.md)

---

## How it works

1. **Constraints are checked, not weighted.** Each hard limit carries a label and an owning
   agent. A violation makes a strategy *infeasible* (score 0), and the owning agent raises it
   as a blocking objection citing the constraint by id.
2. **Formulas from the LLM, arithmetic from a sandbox.** Agents never compute — they state
   lever preferences and 0–1 signals. A whitelisted Python `ast` evaluator computes every
   number: no attribute access, no imports, no `__builtins__`, unknown names rejected before
   compilation. Hostile inputs are in the module's own self-check.
3. **Specialisation is structural.** Every variable carries `visible_to`. Marketing literally
   cannot see the segment default rates, so it cannot drift into Credit Risk's job. In the
   TC1 run Credit Risk sees 10 of 22 variables.
4. **The same field is the impact map.** On a surprise, changed variables map through
   `visible_to` to exactly the agents that must reconsider; everyone else keeps their
   position, recorded with a stated reason.
5. **The search finds what is feasible; the board decides what is wise.** The search ranks on
   money alone; agent signals arrive afterwards and can reorder it. The brief itself says
   *"do not approve a strategy solely because it maximizes short-term revenue."*

Five-stage protocol: **generate → analyse → share → challenge → compare → decide**, capped at
three debate rounds. Decision output is validated in code against the theme's eight mandated
sections, with one repair retry and deterministic backfill.

**Reliability:** a five-rung ladder per LLM call — primary → retry → secondary model →
last-good cache → neutral stub — that never raises. Degraded agents are recorded and
confidence is discounted 0.8× each.

Full technical detail: [`submission/REPORT.md`](submission/REPORT.md)

---

## Layout

```
boardroom/     the engine (13 modules, ~1,480 lines of production code)
prompts/       4 templates — department, CEO, challenge, intake
cases/         themeA_tc1.json (FINSWARM), themeC_tc1.json (CHIPSWARM)
briefs/        raw test-case text + surprise deltas
evidence/      recorded live runs, replayable offline
submission/    test-case transcripts + technical report
docs/          design docs written before the build
```

## Disclosures

- **AI coding assistance** was used during development, as permitted by the rulebook.
  Architecture decisions, case-pack modelling, constraint sets and the hand-computed optima
  were authored and verified by the team.
- **Runtime models:** Gemini 3 Flash (preview) primary, Gemini 3.1 Flash Lite fallback.
- **Dependencies:** `pydantic`, `streamlit`, `google-generativeai`, with optional `openai`
  and `anthropic` adapters. Everything else is the Python standard library.
- **Data:** the organisers' synthetic test-case figures only. No external or personal data.
  No secrets committed; keys are read from the environment or a gitignored `.env`.
- **Known limitations:** candidate search is stochastic (seeded, reproducible) and lands
  within ~1% of the true optimum; intake requires a live LLM provider; agent prose varies run
  to run while the deterministic numbers, constraints and rankings do not.
