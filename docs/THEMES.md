# THEMES — the published test cases

Source: `Agent Swarm Test Cases.pdf`. Three themes, five test cases each, **fifteen scenarios
published in advance**. TC1 is the baseline; TC2–TC4 are surprises; **TC5 is a live test** in
every theme.

This file is the domain reference. Nothing here is code.

---

## 1. What the PDF changes about our plan

Four findings, in order of how much they cost us if missed.

### 1.1 The agent roster is dictated, and it isn't ours

| Theme | Mandatory agents | Count |
|---|---|---:|
| **A — FINSWARM** | Business Research, Finance & Treasury, **Credit Risk**, Marketing & Sales, **Compliance & Customer Protection**, CEO | **6** |
| **B — SAASSWARM** | Market Research, **Product**, **Engineering**, Finance, Marketing & Sales, **Customer Success**, CEO | **7** |
| **C — CHIPSWARM** | Market Research, Finance, **Manufacturing**, **Supply Chain**, **Quality & Reliability**, Marketing & Sales, CEO | **7** |

Our planned roster (Research / Finance / Marketing / Operations / Risk / CEO) matches **none**
of them. Two consequences:

- **The roster becomes case-pack data, not a Python constant.** `DEPARTMENTS` moves into the
  pack. This was already the right design; now it's mandatory.
- **The 8-agent cap gets tight.** B and C mandate 7. Chief of Staff as a judged agent would
  put us at 8 with zero headroom, so it demotes to a **disclosed pre-board intake tool**
  (rulebook §2: *"Background utility functions, databases and deterministic tools do not
  count as agents"*). If a judge insists it counts, we're at 8 — still legal. Either reading
  is compliant, which is the point.

### 1.2 Every fact is supplied — do not infer

All three themes state it: *"Every fact required for the decision will be supplied in the
active test case."*

This **shrinks the Chief of Staff's job to extraction**, and that's good news — extraction
from a structured brief is far more reliable than inference. But it also means an intake that
invents numbers is now actively wrong, not merely risky.

New intake rule: **prefer a gap over an invention.** If a value isn't in the brief, emit it
with `source: "assumption"` and a loud note, or leave the metric out. Never quietly fill.

### 1.3 These are constrained optimization problems, not soft strategy essays

Theme A TC1 has **eight** hard constraints over four decision variables. Theme C TC1 is a
textbook capacity-allocation LP. Theme B TC1 is a knapsack over engineer-months.

Our current design — Chief of Staff invents 3–4 fixed candidate strategies, calculator scores
them — is **too weak for this**:

- Theme A asks for *"one primary segment or a justified portfolio mix"* and Theme C asks
  *"how many units of each product"*. The answer is a **vector**, not a menu pick.
- Constraints must be **checked**, not weighted. A portfolio breaching the 5% default limit
  is invalid, not low-scoring.
- **Judges can verify the arithmetic.** These have near-exact optima.

This forces two additions to the architecture (both in ARCHITECTURE §4–5):
a **constraints block** evaluated by the sandbox, and a **bounded candidate generator** that
searches the lever space and hands the board real feasible optima to argue about.

Upside: this produces the best answer to *"why do you need agents if you have a solver?"* —

> The search finds what is **feasible and near-optimal**. The board decides what is **wise**.
> Theme C TC1 says *"Strategic note: two long-term industrial customers."* That's not in any
> formula, and it's exactly the kind of thing that moves a decision.

### 1.4 The surprises are not all deltas

Theme A TC2 (credit-risk spike) is roughly a fact delta on TC1. But **TC3 (marketing budget
cut) and TC4 (verification capacity) have entirely different lever spaces and metrics** —
channel allocation, reviewer headcount. They are new decision models, not perturbations.

So `surprise` needs two modes:

- **delta mode** — `--facts delta.json`, variables change, pack structure holds
- **re-intake mode** — `--brief tc3.txt`, new pack, but carry forward the prior decision and
  objections so it reads as adaptation rather than a cold start

Both derive affected agents the same way: diff the packs, union the `visible_to` of changed
and new variables. ~20 extra lines, covers the real test structure.

---

## 2. Theme recommendation: **A — FINSWARM** (backup: C)

| | A — FinNova | B — OrbitFlow | C — IndusCompute |
|---|---|---|---|
| Mandatory agents | **6** (most headroom) | 7 | 7 |
| TC1 constraint richness | **8 hard constraints** | ~4 | 6 |
| Arithmetic cleanliness | clean | mixed/qualitative | **cleanest** |
| Built-in disagreement | **Credit Risk vs Marketing vs Compliance, structural** | Product vs Engineering | Manufacturing vs Supply Chain |
| Judge-verifiable optimum | yes | partly | yes |
| Guardrail trap risk | protected characteristics | overclaiming capabilities | inventing specs |

**Pick A.** Three reasons:

1. **Six mandatory agents** — the only theme with real headroom under the cap.
2. **The richest hard-constraint set**, which is exactly what our constraint engine showcases.
3. **The disagreement is in the numbers, not manufactured.** See §3.3 — the profit-maximizing
   portfolio *breaches the 70% concentration limit*, and the feasible optimum excludes retail
   shops entirely, which Compliance and Marketing both have legitimate grounds to fight.
   We do not have to invent a conflict; we have to referee one.

Theme C is the backup — cleanest math, but 7 mandatory agents and a "don't invent
semiconductor specs" trap.

---

## 3. Theme A — FINSWARM reference

**Company:** FinNova Capital, fictional Indian digital lender to registered small businesses.
All currency INR. `1 lakh = 100,000`, `1 crore = 10,000,000`.

**Objective language (goes in the CEO prompt verbatim):**
> Balance sustainable growth, affordability, expected credit losses, liquidity, operational
> capacity, fair customer treatment and compliance. **Do not approve a strategy solely because
> it maximizes short-term revenue.**

**Required decision content — eight items, all validated in code:**
customer segment · product terms · approval policy · budget allocation · risk limits ·
go-to-market approach · implementation sequence · measurable outcomes

**Guardrails:**
- Synthetic corporate strategy exercise, **not personal financial advice**
- **Do not infer protected characteristics or recommend discriminatory lending**

### 3.1 TC1 baseline — launch the small-business loan

Capital 30 cr · acquisition budget 60 lakh · product setup 18 lakh (from acquisition) ·
max 700 loans · cost of funds 10%/yr · servicing 1.5% of principal/yr

| Segment | Avg loan | Default | Demand | Acq cost |
|---|---:|---:|---:|---:|
| Retail shops | ₹4 lakh | 5.0% | 1,500 | ₹2,000 |
| Service SMEs | ₹6 lakh | 3.5% | 900 | ₹3,500 |
| Small manufacturers | ₹9 lakh | 4.5% | 450 | ₹5,500 |

**Levers:** `n_retail`, `n_sme`, `n_mfg` (integers), `interest_rate` (≤ 0.19)

**Constraints:**
```
portfolio_default_pct <= 0.05
interest_rate         <= 0.19
max_segment_share     <= 0.70          # of deployed capital
undeployed_capital    >= 30000000      # ₹3 crore liquidity reserve
n_retail + n_sme + n_mfg <= 700
n_retail <= 1500 ; n_sme <= 900 ; n_mfg <= 450
acquisition_spend <= 4200000           # 60 lakh - 18 lakh setup
```

**Decision question:** which segment mix, pricing, approval policy and launch plan creates the
strongest risk-adjusted business outcome?

### 3.2 TC2–TC5 inventory

| TC | Kind | What changes | Mode |
|---|---|---|---|
| **TC2** Credit-risk spike | surprise | Defaults → 8% / 5% / 7%; risk committee caps portfolio default at **5.5%**; tighter approval cuts eligible demand 25%; pausing costs ₹12 lakh sunk; all changes must be operable within 30 days | **delta** |
| **TC3** Marketing budget cut | surprise | Acquisition budget 60 → 36 lakh (18 lakh usable). New lever space: 4 channels with cost-per-qualified-application and funding conversion; ≥400 qualified applications, ≥160 funded; no channel >65% of spend; referrals capped at 120; launch delay ≤2 weeks | **re-intake** |
| **TC4** Stricter verification | surprise | Ownership + bank-statement verification before disbursal; automation clears 60%, 40% manual; options: hire 4 temps at ₹45k/mo, cut intake, appointment onboarding, delay ≤4 weeks, automated integration ₹8 lakh / 2 weeks. Budget ₹15 lakh / 3 months; median approval <48h; complaints <2% | **re-intake** |
| **TC5** Funding-cost + fraud shock | **LIVE** | Cost of funds 10% → **13%**; retail suspected fraud 2% → **7%**. Controls: fraud screening ₹1,200/retail application cutting fraud 60%, reduce retail allocation, price up to 19%, manual review, cut deployment, delay retail. Limits: ≥₹3 cr liquid, portfolio default ≤5.5%, price ≤19% | **delta** |

TC5 explicitly asks: *"Identify which original assumptions are no longer valid."* That is our
impact-map output, stated as a requirement. Build the diff view to answer it literally.

### 3.3 Expected shape of the TC1 answer — **hand-computed, verified against the pack 2026-09-01**

> **Correction.** An earlier draft of this section maximised per-*loan* contribution against
> the 70% concentration cap and got `n_mfg 426 / n_sme 274`, net ≈ ₹1.48 cr. That is wrong:
> ₹30 crore of capital funds only ~₹27 crore of loans after the ₹3 crore reserve, and
> 426 mfg + 274 SME needs ₹54.78 crore that does not exist. The binding constraint is
> **capital**, not the 700-loan cap. Corrected below and checked in `boardroom/oracles.py`.

Per-loan net contribution at the 19% rate cap (spread = 19% − 10% funding − 1.5% servicing = 7.5%):

| Segment | Spread | Credit loss | Acq | Net / loan | **Net per ₹ deployed** |
|---|---:|---:|---:|---:|---:|
| Retail (₹4L) | 30,000 | 20,000 | 2,000 | ₹8,000 | **0.0200** |
| Service SME (₹6L) | 45,000 | 21,000 | 3,500 | ₹20,500 | **0.0342** |
| Manufacturer (₹9L) | 67,500 | 40,500 | 5,500 | ₹21,500 | **0.0239** |

Capital is scarce (₹27 cr deployable), so the right ranking is **net per rupee deployed**:
**SME first**, then manufacturers, retail last. Concentration then forces ≥30% of the book
outside SME, so the optimum is SME at the 70% cap with the remainder in manufacturers:

```
n_retail 0 · n_sme 315 · n_mfg 90 · rate 19%
deployed ₹27.0 crore   net ≈ ₹0.66 crore (₹6,592,500, after ₹18 lakh setup)
binding: liquidity (₹3 cr reserve exact) · concentration (SME = 70% exact) · rate (19%)
portfolio default ≈ 3.8%   acquisition spend ₹16.0 lakh of ₹42 lakh
```

**The naive answer** — fill the 700-loan cap with the two highest-margin segments,
`n_mfg 450 / n_sme 250` — is **doubly infeasible**:

- **liquidity / capital:** deployed ₹55.5 crore against ₹30 crore of capital. Undeployed
  would be *−₹25.5 crore*. Finance owns this breach.
- **concentration:** manufacturers land at ~73% of the book against the 70% cap. Credit Risk
  owns this one.

**This is the demo, and it writes itself:**

- The naive profit-maximizing answer is **arithmetically infeasible** on two counts — the
  constraint engine catches both deterministically, each with a named owner, not as an
  LLM opinion. "They are asking to lend ₹55 crore when the pilot has ₹30."
- The feasible optimum **serves zero retail shops** — the largest demand pool (1,500) and the
  smallest businesses — because retail is the worst return per rupee of scarce capital *and*
  carries the highest default (5%).
- **Compliance & Customer Protection** has legitimate grounds to object on fair treatment:
  a small-business lender that funds no small shops.
- **Marketing & Sales** objects: retail is the growth base and ₹26 lakh of the acquisition
  budget goes unspent.
- **Credit Risk** defends the exclusion: retail's 5% default is what tips the portfolio.
- The brief itself says *do not approve a strategy solely because it maximizes short-term
  revenue* — so the CEO **should** weigh a retail tranche and justify the trade-off.

Three departments, three legitimate positions, a numerically forced trade-off, and an explicit
instruction not to just take the money. We referee; we don't manufacture.

Use these figures as the **Phase 0 test oracle**: the generator should land near `0/315/90`
at 19% with net in `[₹6.4M, ₹6.8M]`, and both seed corner strategies must come back infeasible
with their constraints named. `python -m boardroom.oracles` checks exactly this.

---

## 4. Theme B — SAASSWARM reference (backup material)

**Company:** OrbitFlow Software, fictional Indian B2B SaaS, AI-assisted workflow platform.

**Required decision content:** target customer · product scope · engineering priorities ·
pricing · sales motion · launch timing · operating safeguards · measurable adoption or revenue

**Guardrails:** *"Do not claim unavailable integrations, certifications, security controls or
AI accuracy. Separate confirmed capabilities from roadmap commitments."* — the sharpest
guardrail of the three; an agent that says "we're SOC 2 compliant" fails the theme.
Also: *"a feature-rich plan is not automatically a better plan."*

### TC1 baseline — choose the product market and MVP
₹2.4 cr · 12 engineers · 9 months · 72 engineer-months pre-launch · ₹70 lakh marketing.
Core platform + admin = 30 em; **42 em allocatable to one segment.**

| Segment | Effort | ACV | Prospects | Conv | Implied yr-1 ARR |
|---|---:|---:|---:|---:|---:|
| Small retailers | 18 em | ₹1.2 L | 220 | 12% | ≈ ₹31.7 L |
| Mid-market services | 28 em | ₹4.5 L | 70 | 20% | ≈ ₹63.0 L |
| Large enterprises | 42 em | ₹15 L | 18 | 28% | ≈ ₹75.6 L |

Targets: ARR ≥ ₹60 L in 12 months · churn < 15% · discounts ≤ 20% of list.
Retailers **miss the ARR target**; enterprise clears it but consumes all 42 em with no slack
across 18 prospects. Mid-market clears with 14 em spare. That's the trade-off.

### TC2–TC5
| TC | What changes |
|---|---|
| **TC2** Competitor price cut | Rival at ₹2.4 L vs our ₹4.5 L. 45% price-sensitive / 35% value implementation / 20% data controls. Fund **either** 6 em of features **or** 4 implementation specialists — not both. Delay past 6 weeks costs 20% of prospects |
| **TC3** Enterprise security | 3 prospects worth ₹54 L ARR need SSO 8 em, RBAC 6 em, audit logs 5 em, CMEK 10 em, security testing ₹12 L + 4 weeks. Have 18 em, ₹15 L, ≤6 weeks delay. **Selling an unimplemented feature is prohibited** |
| **TC4** Outages and churn | 40 customers, ₹1.5 cr ARR, churn 1% → 3%. Causes: 50% reliability, 30% support, 20% features. 20 em + ₹12 L. ≥4 em reserved for maintenance; churn must fall below 1.5% in a quarter |
| **TC5** Strategic customer **LIVE** | ₹60 L/yr two-year deal needs private deployment in 12 weeks: 24 em + ₹8 L infra + ₹6 L support. Delays roadmap 8 weeks, risking 3 opportunities worth ₹45 L combined at 40% close each. 6 months runway, 8 engineers, ₹30 L discretionary. Termination right if >2 weeks late |

---

## 5. Theme C — CHIPSWARM reference (backup material)

**Company:** IndusCompute Hub, fictional Indian GPU module assembly, advanced packaging and
test. **Does not fabricate wafers.**

**Required decision content:** production mix · capacity calculation · procurement and
inventory actions · quality controls · customer communication · financial effect ·
implementation sequence

**Guardrails:** *"Do not invent semiconductor specifications. Treat all product and process
values as synthetic planning data."*

### TC1 baseline — allocate production capacity
24,000 machine-hours next month.

| Product | h/unit | Margin/unit | Max demand | Min commit | Margin per machine-hour |
|---|---:|---:|---:|---:|---:|
| AI accelerator | 6 | ₹45,000 | 2,500 | 800 | **₹7,500** |
| Gaming board | 2 | ₹10,000 | 6,000 | 2,000 | ₹5,000 |
| Edge module | 3 | ₹18,000 | 3,500 | 1,000 | ₹6,000 |

Constraints: no line > 65% of total machine-hours (15,600) · ≥1,200 h disruption buffer unless
the CEO explicitly justifies using part of it · production ≤ max demand.

**Hand-computed oracle — checked in `boardroom/oracles.py` (2026-09-01):**
```
AI 2,500 (15,000 h, demand-bound, best margin/hour at ₹7,500)
Gaming 2,000 (4,000 h, committed minimum)
Edge 1,266 (3,798 h, absorbs the remainder)
total 22,798 h of 22,800 usable (1,200 h buffer preserved)
contribution margin ≈ ₹15.53 crore   (112.5M AI + 20.0M gaming + 22.79M edge)
```
An earlier draft said ₹13.73 crore — a transcription error; the figures above reconcile.
The buffer is an *explicitly overridable* constraint — a built-in CEO-override moment.
`cases/themeC_tc1.json` is hand-built; the naive "fill every line to demand" seed is
rejected on `capacity` (37,500 h against 22,800 usable).

### TC2–TC5
| TC | What changes |
|---|---|
| **TC2** Component delay | HBM supplier caps AI at 1,100 units; backup adds 500 at −₹9,000 margin each and ₹15 L unskippable qualification. Signed minimum of 1,500 AI modules; each unit short costs a ₹6,000 service credit. Freed hours reallocatable; buffer drops to 800 h |
| **TC3** AI demand + energy surge | AI demand → 3,200; electricity +35%; margins fall ₹4,000 / ₹1,000 / ₹1,500. Weekend shift adds ≤3,000 h for ₹28 L fixed, +20% inspection workload, and reserves 600 regular hours for inspection/rework. Line cap loosens to 70% |
| **TC4** Packaging-yield decline | Final yield 94% → 82% on 2,000 starts; must ship ≥1,700 saleable. Options: 3-day calibration (starts → 1,850, yield → 92%), enhanced inspection ₹3,000/start for 86% effective yield, outsource ≤300 at −₹12,000 margin. ₹8,000 service credit per unit short |
| **TC5** Export restriction **LIVE** | Plan 1,600 AI / 4,000 gaming / 1,800 edge. 25% of AI and 30% of gaming were bound for one overseas market, now blocked. Domestic absorbs +250 AI at full margin, +700 gaming at 80% margin. Storage ₹2,000/AI/mo, ₹500/gaming/mo. No conversion between products. ≤₹18 L extra storage and working capital |

---

## 6. Is our solution still "generic"?

Short answer: **yes, and we should stop selling it that way.**

The themes are published. "Works on an unseen problem" is no longer the differentiator it was
two hours ago — the organizers handed us all fifteen scenarios.

But generality is still load-bearing, for three concrete reasons:

1. **The roster differs per theme**, so roster-as-data is a hard requirement now.
2. **TC3 and TC4 change the lever space**, so pack regeneration is a hard requirement now.
3. **TC5 is live**, so a fast, reliable adaptation path is a hard requirement now.

**Reframe the claim — this is the important edit to the pitch:**

> ~~"It works on any business problem."~~
> **"It runs all fifteen of your published test cases without a code change — here's the one
> we didn't prepare, live."**

That version is *weaker on paper and far stronger in the room*, because it is checkable. Every
other team will build for their chosen theme's TC1 and bolt on the surprise. Being able to
hand a judge the theme we did **not** pick, run it cold, and produce a full board decision is
the single most convincing thing we can do in the Q&A — and it costs us nothing beyond the
Phase 0 drill we were already planning.
