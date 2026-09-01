# ARCHITECTURE — build spec

Target ~800 lines of Python. `pydantic` + one LLM SDK + `streamlit`. Everything else stdlib.
No agent framework, no solver library.

**Invariant: no Python file is domain-specific.** The agent roster, the metrics, the
constraints and the guardrails all live in the case pack. See `THEMES.md` for why that's now
mandatory rather than elegant — the three themes mandate three different rosters.

```
boardroom/
  state.py        # Pydantic models — the only shared contract
  llm.py          # one call() with retry + model fallback + JSON repair
  intake.py       # brief -> case_pack.json -> validate   (pre-board tool, not an agent)
  calculator.py   # GENERIC AST-sandbox: metrics + constraint checks. No domain logic.
  generate.py     # GENERIC bounded search over the lever space -> feasible candidates
  scoring.py      # GENERIC weighted score over role-mapped metrics
  agents.py       # roster loaded from the pack; one function drives every role
  engine.py       # 5-stage protocol + selective re-run + degraded mode
  cli.py          # python -m boardroom intake|run|surprise|replay
  viewer.py       # streamlit, read-only over runs/*.json
prompts/
  _department.md  _ceo.md     # two templates; the role text comes from the pack
cases/
  themeA_tc1.json … themeC_tc5.json     # all 15, built in Phase 0
briefs/
  themeA_tc1.txt … themeC_tc5.txt       # raw text lifted from the PDF
runs/
  <ts>_baseline.json  <ts>_surprise.json  GOLDEN_*.json
```

---

## 1. Case pack schema — the contract between domain and engine

The most important object in the system. Everything domain-specific lives here and nowhere else.

```jsonc
{
  "case_id": "themeA_tc1",
  "theme": "FINSWARM",
  "problem": "one paragraph restating the situation",
  "decision_question": "the single question the CEO must answer",

  // ── who sits on this board (THEMES §1.1: differs per theme) ─────────────
  "roster": [
    { "id": "research",   "title": "Business Research Agent",
      "mandate": "Analyse market, customers, competitors, opportunity and risk.",
      "signals": ["demand_confidence"] },
    { "id": "finance",    "title": "Finance and Treasury Agent",
      "mandate": "Evaluate cost, revenue, funding, liquidity and profitability.",
      "signals": ["margin_health", "liquidity_health"] },
    { "id": "credit_risk","title": "Credit Risk Agent",
      "mandate": "Assess expected credit losses, concentration and portfolio quality.",
      "signals": ["risk_score"] },
    { "id": "marketing",  "title": "Marketing and Sales Agent",
      "mandate": "Target segments, positioning, channels, acquisition.",
      "signals": ["customer_impact", "growth_potential"] },
    { "id": "compliance", "title": "Compliance and Customer Protection Agent",
      "mandate": "Fair treatment, affordability, regulatory and conduct risk.",
      "signals": ["compliance_health"] }
  ],
  "ceo": { "title": "CEO Agent",
           "objective": "Balance sustainable growth, affordability, expected credit losses, liquidity, operational capacity, fair customer treatment and compliance. Do not approve a strategy solely because it maximizes short-term revenue." },

  // ── the theme's hard prohibitions, injected into EVERY prompt ───────────
  "guardrails": [
    "This is a synthetic corporate strategy exercise, not personal financial advice.",
    "Do not infer protected characteristics or recommend discriminatory lending."
  ],

  // ── what the CEO output must contain, checked in code ──────────────────
  "required_decision_fields": [
    "customer_segment", "product_terms", "approval_policy", "budget_allocation",
    "risk_limits", "go_to_market", "implementation_sequence", "measurable_outcomes"
  ],

  "variables": [
    { "key": "capital", "value": 300000000, "unit": "INR", "source": "case_pack",
      "visible_to": ["finance", "credit_risk"], "note": "" },
    { "key": "retail_default", "value": 0.05, "unit": "fraction", "source": "case_pack",
      "visible_to": ["credit_risk", "research"], "note": "" }
  ],

  "levers": [
    { "key": "n_retail", "min": 0, "max": 1500, "step": 1,    "owner": "marketing" },
    { "key": "n_sme",    "min": 0, "max": 900,  "step": 1,    "owner": "marketing" },
    { "key": "n_mfg",    "min": 0, "max": 450,  "step": 1,    "owner": "marketing" },
    { "key": "rate",     "min": 0.12, "max": 0.19, "step": 0.005, "owner": "finance" }
  ],

  "metrics": {
    "deployed":              "n_retail*retail_loan + n_sme*sme_loan + n_mfg*mfg_loan",
    "credit_loss":           "n_retail*retail_loan*retail_default + n_sme*sme_loan*sme_default + n_mfg*mfg_loan*mfg_default",
    "interest_income":       "deployed * rate",
    "funding_cost":          "deployed * cost_of_funds",
    "servicing_cost":        "deployed * servicing_rate",
    "acquisition_spend":     "n_retail*retail_acq + n_sme*sme_acq + n_mfg*mfg_acq",
    "net_income":            "interest_income - credit_loss - funding_cost - servicing_cost - acquisition_spend - setup_cost",
    "portfolio_default_pct": "credit_loss / max(deployed, 1)",
    "undeployed_capital":    "capital - deployed",
    "max_segment_share":     "max(n_retail*retail_loan, n_sme*sme_loan, n_mfg*mfg_loan) / max(deployed, 1)",
    "total_loans":           "n_retail + n_sme + n_mfg"
  },

  // ── HARD constraints. Violation = infeasible, not low-scoring. ──────────
  "constraints": [
    { "id": "default_cap",    "expr": "portfolio_default_pct <= 0.05",
      "label": "Expected portfolio default must remain at or below 5%",     "owner": "credit_risk" },
    { "id": "rate_cap",       "expr": "rate <= 0.19",
      "label": "Average annual customer interest must not exceed 19%",      "owner": "compliance" },
    { "id": "concentration",  "expr": "max_segment_share <= 0.70",
      "label": "No segment may receive more than 70% of deployed capital",  "owner": "credit_risk" },
    { "id": "liquidity",      "expr": "undeployed_capital >= 30000000",
      "label": "At least INR 3 crore must remain undeployed",               "owner": "finance" },
    { "id": "loan_cap",       "expr": "total_loans <= 700",
      "label": "Total approved loans cannot exceed 700",                    "owner": "operations" },
    { "id": "acq_budget",     "expr": "acquisition_spend <= 4200000",
      "label": "Acquisition spend within budget after setup cost",          "owner": "marketing" },
    { "id": "demand_retail",  "expr": "n_retail <= 1500", "label": "Retail demand cap",   "owner": "research" },
    { "id": "demand_sme",     "expr": "n_sme <= 900",     "label": "SME demand cap",      "owner": "research" },
    { "id": "demand_mfg",     "expr": "n_mfg <= 450",     "label": "Manufacturer demand cap", "owner": "research" }
  ],

  "direction": { "net_income": "max", "portfolio_default_pct": "min", "deployed": "max" },
  "objective": "net_income",              // what the candidate generator ranks on

  "score_inputs": {
    "value":       "net_income",
    "efficiency":  "metric:portfolio_default_pct",       // direction handles the inversion
    "feasibility": "signal:liquidity_health",
    "customer":    "signal:customer_impact",
    "risk":        "signal:risk_score"
  },
  "weights": { "value": 0.30, "efficiency": 0.25, "feasibility": 0.20,
               "customer": 0.15, "risk": 0.10 },

  "seed_strategies": [                    // corner cases, always included for contrast
    { "id": "S_retail", "name": "Retail-led volume",   "levers": {"n_retail": 700, "n_sme": 0, "n_mfg": 0, "rate": 0.19} },
    { "id": "S_mfg",    "name": "Manufacturer-led",    "levers": {"n_retail": 0, "n_sme": 250, "n_mfg": 450, "rate": 0.19} }
  ]
}
```

`visible_to` does double duty — the per-agent **fact filter** and the **impact map**.
`constraints[].owner` does double duty too: it tells us which agent gets to *speak for* a
violated constraint in the debate, which is how a numeric infeasibility becomes a business
argument.

### Qualitative packs

Theme B TC3 (security roadmap) and TC4 (churn causes) are only half-numeric. The Chief of
Staff must still emit **≥3 computable metrics** built from supplied figures, and
`score_inputs` may fall back to `signal:*` for every role. The board still functions;
document this because a judge may probe it.

---

## 2. Intake (`intake.py`) — a pre-board tool, not an agent

Positioned outside the judged agent count (rulebook §2: *utility functions and deterministic
tools do not count as agents*). Themes B and C mandate 7 agents; we need the headroom.
**Disclose it in the README either way** — if a judge counts it, we're at 8, still legal.

```
raw brief (text)
   ↓  LLM, one call, strict JSON schema
case_pack.json
   ↓  validate() — deterministic, no LLM
   ├─ roster non-empty; every roster id unique; ceo present
   ├─ every variable has key/value/source/visible_to
   ├─ every visible_to entry is a roster id
   ├─ every metric AND constraint expression PARSES in the sandbox
   ├─ every name resolves to a variable, lever, or earlier metric
   ├─ metrics + constraints evaluate on every seed strategy without exception
   ├─ ≥3 metrics, ≥1 constraint, ≥2 seed strategies
   ├─ score_inputs keys ⊆ metrics ∪ signals declared in the roster
   ├─ weights sum to 1.0 (±0.01)
   └─ guardrails and required_decision_fields non-empty
   ↓  fail → ONE repair retry with the exact error list appended
   ↓  fail again → human patches the JSON (budget 10 min)
validated pack
```

**Extraction, not inference.** All three themes state *"every fact required for the decision
will be supplied in the active test case."* The intake prompt says so explicitly:

> Extract only what the brief states. If a value the metrics need is absent, emit it with
> `source: "assumption"` and a note explaining the gap. **Never quietly invent a number.**
> Prefer omitting a metric over fabricating an input for it.

---

## 3. Sandbox evaluator (`calculator.py`) — ~70 lines, stdlib only

An LLM writes the expressions, so treat them as semi-untrusted. Whitelist the AST; never
`eval` raw.

```python
import ast, math

ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.IfExp,
           ast.Call, ast.Name, ast.Load, ast.Constant,
           ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd,
           ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.And, ast.Or, ast.Not)

FUNCS = {"min": min, "max": max, "abs": abs, "round": round,
         "exp": math.exp, "sqrt": math.sqrt, "log": lambda x: math.log(max(x, 1e-9))}

def safe_eval(expr: str, ns: dict):
    tree = ast.parse(expr, mode="eval")
    for n in ast.walk(tree):
        if not isinstance(n, ALLOWED):
            raise ValueError(f"disallowed syntax {type(n).__name__} in {expr!r}")
        if isinstance(n, ast.Call) and (not isinstance(n.func, ast.Name) or n.func.id not in FUNCS):
            raise ValueError(f"disallowed call in {expr!r}")
        if isinstance(n, ast.Name) and n.id not in ns and n.id not in FUNCS:
            raise ValueError(f"unknown name {n.id!r} in {expr!r}")
    return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, {**FUNCS, **ns})

def compute(metrics: dict[str, str], ns: dict) -> dict[str, float]:
    """Metrics may reference earlier metrics; resolve by repeated passes."""
    out, pending = dict(ns), dict(metrics)
    for _ in range(len(metrics) + 1):
        if not pending:
            break
        progressed = False
        for k, expr in list(pending.items()):
            try:
                out[k] = safe_eval(expr, out); del pending[k]; progressed = True
            except ValueError:
                pass                      # unresolved name — retry next pass
        if not progressed:
            raise ValueError(f"unresolvable or circular metrics: {sorted(pending)}")
    return {k: out[k] for k in metrics}

def check(constraints: list[dict], ns: dict) -> list[dict]:
    """Returns the list of VIOLATED constraints, each with its label and owner."""
    return [c for c in constraints if not safe_eval(c["expr"], ns)]
```

No attribute access, no subscripting, no imports, no comprehensions, no `__builtins__`.
Unknown names are rejected before compilation.

**Self-check (`demo()` under `__main__`, assert-based).** Must include:
`__import__('os')` → raises · `().__class__` → raises · circular metrics → raises ·
divide-by-zero guarded · **and the Theme A TC1 oracle from THEMES §3.3** — feed
`n_mfg=426, n_sme=274, n_retail=0, rate=0.19`, assert zero violated constraints and
`net_income` ≈ ₹1.48 crore. That last one catches a wrong pack, not just wrong code.

---

## 4. Candidate generator (`generate.py`) — new, and it's what makes the answers defensible

THEMES §1.3: these are constrained optimization problems with near-exact optima that judges
can check with a calculator. Letting an LLM pick three round numbers loses Business Value.

Bounded random search. No solver dependency, ~35 lines.

```python
def candidates(pack, n_samples=20000, k=5) -> list[Strategy]:
    ns0 = {v["key"]: v["value"] for v in pack["variables"]}
    feasible = []
    for _ in range(n_samples):
        levers = {L["key"]: sample(L) for L in pack["levers"]}      # respects min/max/step
        try:
            m = compute(pack["metrics"], {**ns0, **levers})
        except ValueError:
            continue
        if check(pack["constraints"], {**ns0, **levers, **m}):
            continue                                                # infeasible, discard
        feasible.append((m[pack["objective"]], levers, m))

    feasible.sort(key=lambda t: -t[0])
    picked = diversify(feasible, k)          # greedy: skip any within 5% lever distance
    return [as_strategy(p) for p in picked] + seed_strategies(pack)   # seeds may be infeasible
```

Three deliberate choices:

- **Seed strategies are always included, even when infeasible.** The Theme A greedy answer
  (450 manufacturers) *breaches the concentration cap* — showing it rejected with the
  constraint named is worth more than hiding it. That's our rejected-alternative evidence,
  arithmetically grounded.
- **Ranking uses the deterministic objective only.** Agent signals don't exist yet at
  generation time. The board's weighted score comes later and may reorder the list — which
  is exactly the story: *search finds what is feasible, the board decides what is wise.*
- **`diversify`** stops the board being handed five near-identical vectors. Greedy skip on
  normalized lever distance; ~8 lines.

20,000 samples over 3–4 levers runs in well under a second and lands within a percent of the
optimum on all three TC1s. If a pack ever needs more precision, raise `n_samples` — there is
no algorithm to swap.

> `ponytail:` random search, not an LP solver. Fine for ≤6 levers with a smooth objective,
> which is every published test case. Swap to `scipy.optimize.linprog` only if a pack appears
> with a genuinely large or integer-nasty lever space.

---

## 5. Scoring (`scoring.py`) — domain-general

Five fixed weight slots; the pack maps each to a metric or an agent signal.

```python
def score(strategy, signals, pack, cohort) -> float:
    if strategy.violations:
        return 0.0                    # a hard constraint breach beats every weight
    parts = {}
    for role, ref in pack["score_inputs"].items():
        if ref.startswith("signal:"):
            parts[role] = clamp01(signals.get(ref[7:], 0.5))
        else:
            key = ref.removeprefix("metric:")
            parts[role] = normalize(strategy.metrics[key], key, pack["direction"], cohort)
    return sum(pack["weights"][r] * parts[r] for r in parts)
```

`normalize` min-maxes across the candidate cohort and inverts when `direction == "min"`.
Weights are visible in the pack and adjustable from the Streamlit sidebar — our one-slider
answer to *"change one input"* under live verification.

---

## 6. Shared state (`state.py`)

Append-only trace. Everything judges want to see is a field.

```python
Source   = Literal["case_pack", "assumption", "surprise", "computed"]
Severity = Literal["minor", "material", "blocking"]

class Variable(BaseModel):
    key: str; value: float | str; unit: str = ""
    source: Source; visible_to: list[str]; note: str = ""

class Violation(BaseModel):
    constraint_id: str; label: str; owner: str; margin: float   # how far over

class Strategy(BaseModel):
    id: str; name: str; levers: dict[str, float]
    metrics: dict[str, float] = {}          # sandbox only — never written by an LLM
    violations: list[Violation] = []        # non-empty => infeasible, score 0
    score: float = 0.0
    verdict: Literal["selected", "rejected", "viable"] = "viable"
    reject_reason: str = ""
    origin: Literal["search", "seed", "agent"] = "search"

class Recommendation(BaseModel):
    agent: str; backs: str                  # strategy id
    claim: str; rationale: str
    lever_view: dict[str, float]
    signals: dict[str, float]               # 0-1 scalars this agent owns
    assumptions: list[str]; confidence: float

class Objection(BaseModel):
    from_agent: str; against: str
    severity: Severity; claim: str; evidence: str
    cites_constraint: str = ""              # constraint id, when grounded in one
    response: str = ""
    outcome: Literal["revised", "defended", "unresolved"] = "unresolved"

class KPI(BaseModel):
    name: str; formula: str; baseline: float; target: float; unit: str

class Step(BaseModel):
    window: str; action: str; owner: str

class Decision(BaseModel):
    statement: str
    sections: dict[str, str]                # keyed by pack.required_decision_fields
    evidence: list[str]
    rejected: list[dict]                    # [{"strategy": id, "reason": str}] — min 1
    tradeoffs: list[str]; risks: list[str]; assumptions: list[str]
    implementation: list[Step]
    kpis: list[KPI]                         # min 3
    overrode_score: bool = False; override_reason: str = ""
    confidence: float

class TraceEvent(BaseModel):
    ts: float; stage: str; agent: str; kind: str; payload: dict

class BoardroomState(BaseModel):
    run_id: str; case_id: str
    pack: dict
    variables: list[Variable]
    strategies: list[Strategy] = []
    recommendations: list[Recommendation] = []
    objections: list[Objection] = []
    decision: Decision | None = None
    trace: list[TraceEvent] = []
    round: int = 0
    degraded: list[str] = []
    parent_run: str | None = None
    reran: list[str] = []
    unchanged: list[dict] = []              # [{"agent":..., "reason":...}]
    invalidated_assumptions: list[str] = [] # TC5 asks for this by name
```

`runs/<ts>.json` is the audit record. Viewer and demo both read it.
**The JSON is the deliverable; the UI is a lens.**

---

## 7. Agents (`agents.py` + two prompt templates)

No per-agent Python. The roster comes from the pack; one function drives every department.

```python
def facts_for(agent_id: str, vars: list[Variable]) -> list[Variable]:
    return [v for v in vars if agent_id in v.visible_to]
```

### Department template (`prompts/_department.md`)

```
You are the {title} of {company}.

DECISION: {decision_question}
{problem}

YOUR MANDATE: {mandate}

GUARDRAILS — these override everything else:
{guardrails}

VARIABLES YOU CAN SEE (you cannot see the others; do not invent any):
{filtered_variables}                 # each tagged FACT or ASSUMPTION

CANDIDATE STRATEGIES (already checked against every hard constraint):
{strategy_table}                     # levers, metrics, violations

CONSTRAINTS YOU OWN: {my_constraints}

RULES
- You do NOT calculate. A sandboxed evaluator computed every number above.
  Never write a currency figure of your own.
- Anything not in VARIABLES is your assumption. List it in `assumptions`.
- You represent {title} only. Do not hedge into other departments' concerns.
- Emit your owned signals in 0..1: {signals}
- Return ONLY JSON matching: {schema}
```

Challenge round appends:

```
Other departments recommended:
{digest}

You MUST return an `objections` array. If a candidate violates a constraint you own, that is
a BLOCKING objection — cite the constraint id. If you genuinely have no material objection,
return one with severity "minor" stating what would have to be true for you to object.
Never fabricate a disagreement.
```

That last clause is load-bearing. LLMs are agreeable; without a required field we get a board
of yes-men and lose 5 points for *meaningful challenge*. Requiring the **field** while
forbidding fabrication is the honest way to force the structure — and in Theme A we don't
have to lean on it, because the constraint arithmetic supplies a real conflict (THEMES §3.3).

---

## 8. The 5-stage protocol (`engine.py`)

Implemented literally so the trace maps 1:1 onto rulebook §3.

```
STAGE 0  GENERATE  candidates() -> feasible optima + seeds, metrics and violations filled
                   (deterministic; happens before any agent runs)
STAGE 1  ANALYSE   ThreadPoolExecutor over the roster, each on its own fact slice
                   -> Recommendation + signals
STAGE 2  SHARE     digest of all recommendations -> state + trace
STAGE 3  CHALLENGE objections; material|blocking -> targeted agent gets ONE rebuttal turn,
                   revises or defends; outcome recorded
                   a violated constraint auto-generates a blocking objection from its owner
STAGE 4  COMPARE   scoring ranks the cohort; violators sink regardless of score
STAGE 5  DECIDE    CEO gets strategies + metrics + violations + ranking + objections
                   + degraded list -> Decision, validated in code, one repair retry
```

Loop control (§3: cap at three review cycles, must terminate):

```python
MAX_ROUNDS = 3
while state.round < MAX_ROUNDS and has_unresolved_material(state):
    state.round += 1
    challenge_round(state)
# hard exit — if still unresolved, the CEO decides on the record and says so
```

Default is one challenge round; round 2 fires only on unresolved material objections.
Keeps a full run under ~90 seconds.

### Decision validation — 15 points live here

```python
def validate(d: Decision, pack: dict) -> list[str]:
    errs = []
    for f in pack["required_decision_fields"]:            # THEME-SPECIFIC, 7-8 items
        if not d.sections.get(f, "").strip():
            errs.append(f"missing required decision section: {f}")
    if len(d.rejected) < 1:  errs.append("need >=1 rejected alternative with a reason")
    if len(d.kpis) < 3:      errs.append("need >=3 KPIs with formula/baseline/target")
    if not d.implementation: errs.append("need an implementation sequence with owning functions")
    if not d.evidence:       errs.append("must cite department evidence")
    if not d.tradeoffs:      errs.append("must state trade-offs")
    if d.overrode_score and not d.override_reason:
        errs.append("override of the ranking must be justified")
    return errs
```

The `required_decision_fields` loop is the cheap half of 15 points. Theme A demands eight
named sections, B eight, C seven (THEMES §3–5). Most teams will produce a generic decision
and silently drop three of them.

Fails → re-prompt the CEO once with the error list. Fails again → backfill deterministically
from the ranked table and set `confidence *= 0.8`.
**Judges never see a CEO output missing a mandatory section.**

---

## 9. Surprise adaptation — two modes

THEMES §1.4: TC2/TC5 are fact deltas; TC3/TC4 change the lever space entirely. Both are
"surprises" and both must work.

```python
def adapt(baseline, *, facts=None, brief=None):
    new = baseline.model_copy(deep=True)
    new.parent_run, new.run_id = baseline.run_id, new_id()

    if facts:                                   # DELTA MODE  (TC2, TC5)
        changed = apply_variables(new, facts, source="surprise")
        new.pack = patch_constraints(new.pack, facts)     # e.g. default cap 5% -> 5.5%
    else:                                       # RE-INTAKE MODE  (TC3, TC4)
        new.pack = intake(brief)                          # new levers, metrics, constraints
        changed = pack_diff(baseline.pack, new.pack)      # changed + new variable keys

    affected = {a for k in changed for a in visible_to(new, k)}
    affected |= {c["owner"] for c in newly_violated(baseline, new)}   # a broken constraint
    unknown  = [k for k in changed if k not in var_keys(baseline)]    # wakes its owner
    if unknown and not brief:
        affected |= roster_ids(new)
        trace(new, "system", "impact_fallback", keys=unknown)

    new.reran     = sorted(affected)
    new.unchanged = [{"agent": a, "reason": f"no dependency on {sorted(changed)}"}
                     for a in roster_ids(new) if a not in affected]
    for u in new.unchanged:
        trace(new, u["agent"], "skipped", **u)

    new.invalidated_assumptions = [               # TC5 asks for this by name
        f"{k}: {baseline_value(k)} -> {new_value(k)}" for k in changed]

    generate(new); rerun(new, new.reran); recompute(new); ceo(new)
    return new
```

Note `invalidated_assumptions` — Theme A TC5 and Theme C TC5 both literally instruct
*"identify which original assumptions are no longer valid."* That's a required output, so
it's a field, not a narrative flourish.

An unmapped variable in delta mode degrades to rerun-all **and says so in the trace**. Never
crash on a surprise we didn't anticipate; degrade visibly.

Demo artifact is a **diff view**: changed variables | invalidated assumptions | who re-ran |
who didn't and why | baseline vs revised decision | KPI deltas.

---

## 10. Reliability (`llm.py`) — 10 points live here

### Fallback ladder, per call
```
1. primary model
2. retry once            (429 / timeout / transient)
3. secondary model
4. last-good cached output for this agent (previous round, or baseline run)
5. neutral stub {"status": "unavailable"} + append to state.degraded
```
Never raises. Never kills a run.

```python
confidence = base_confidence * (0.8 ** len(state.degraded))
```

CEO prompt receives: *"Credit Risk is unavailable; you are using its last validated output.
Reflect this in your confidence and flag it under risks."*

### JSON repair
`json.loads` fails → one retry with the parse error appended. No `instructor`, no extra dep.

### Demo fail-safe
Every run writes `runs/<ts>.json`. `python -m boardroom replay runs/<ts>.json` renders the
full board with **zero network calls**. §7 explicitly permits a saved trace to support the
demo. Record golden runs at Phase 6; never overwrite.

### The demanded failure path
`python -m boardroom run --fail credit_risk` kills an agent deliberately. The board still
decides, confidence drops, a warning renders. 30 seconds of demo for *fallback 2* +
*reliability 3* — and it's the single most-skipped requirement in the rulebook.

---

## 11. CLI

```bash
python -m boardroom intake   --brief briefs/themeA_tc1.txt --out cases/themeA_tc1.json
python -m boardroom run      --case cases/themeA_tc1.json
python -m boardroom surprise --run runs/GOLDEN_baseline.json --facts briefs/themeA_tc2.json
python -m boardroom surprise --run runs/GOLDEN_baseline.json --brief briefs/themeA_tc3.txt
python -m boardroom replay   runs/GOLDEN_baseline.json
python -m boardroom run      --case cases/themeA_tc1.json --fail credit_risk
streamlit run boardroom/viewer.py
```

The CLI is the system. Streamlit is a lens over the same JSON. If Streamlit dies at 7:30 we
demo the CLI and lose only polish — worth zero points.

---

## 12. Optional: policy simulation (only if Phase 7 lands early)

Freeze the CEO's chosen lever vector, perturb the pack's variables within stated ranges, and
re-run `compute()` + `check()` — no LLM calls, so 1000 scenarios cost nothing.

```python
for _ in range(1000):
    ns = perturb(pack_variables, sigma=0.15)
    compare(seed_greedy, seed_conservative, ceo_choice, ns)
```

One honest sentence for the pitch:
> "Across 1000 perturbations of the stated inputs, the board's portfolio stayed within every
> hard constraint in X% of scenarios versus Y% for the profit-maximizing alternative.
> Simulated, not field data."

**Strictly optional.** Skipping costs nothing on the rubric.
