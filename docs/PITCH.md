# PITCH — 8-minute slot

Rulebook §7 fixes the segment budget. Six minutes of us, two of them.

| Segment | Max | Slide |
|---|---:|---|
| Problem and value | 1:00 | 1 |
| Swarm design | 1:00 | 2 |
| Live/recorded trace demo | 3:00 | 3 (mostly screen) |
| Surprise adaptation + closer | 1:00 | 4 |
| Judge questions | 2:00 | 5 as backdrop |

> **DEMO PRIORITY** (rulebook): *"Spend presentation time showing agent interaction and
> business reasoning. A polished interface cannot substitute for a weak swarm."*

Half our airtime is the trace. Design the talk around it.

Written for **Theme A — FINSWARM**. Swap the numbers for Theme C if we pivot; the beats hold.

---

## Five slides

**1 — The decision, not the forecast**
FinNova's situation in four numbers: ₹30 crore, 700 loans, three segments, eight constraints.
> "They don't need a credit model. They need a portfolio they can defend to a risk committee."

**2 — The board**
Six agents, the theme's mandated roster, each labelled with **what only it can see** and
**which constraint only it can veto**. Credit Risk owns the default and concentration caps;
Compliance owns the rate cap. Intake shown below the line as tooling, not an agent.

**3 — Boardroom trace** (screen)

**4 — Before / after the shock**
Changed variables · invalidated assumptions · who re-ran · **who didn't and why** · both
decisions · KPI deltas.

**5 — Impact + how it's built**
KPIs with baselines. Architecture thumbnail. Reproducibility: clone, `pip install -r`, one
command.

---

## Script

### 0:00–1:00 — Problem and value

> FinNova has ₹30 crore, room for 700 loans, three customer segments, and eight hard limits —
> a 5% portfolio default cap, a 19% rate ceiling, a 70% concentration limit, a liquidity
> reserve.
>
> The question isn't *who will default* — a credit model answers that. It's *which portfolio
> to actually write*. And that question has no single owner. Treasury wants the spread. Credit
> Risk wants the loss rate down. Compliance has to sign off that we treated small shops fairly.
>
> Today that's a committee that meets for a week. We built the committee.

### 1:00–2:00 — Swarm design

> Six agents — the roster this theme mandates. The roster isn't in our code; it's in the case
> file, along with the variables, the formulas and the constraints. Nothing in our Python
> knows this is a lending problem.
>
> Three design decisions:
>
> **Each agent sees a different slice of the facts.** Marketing cannot see the segment default
> rates. It cannot drift into Credit Risk's job, because it doesn't have the data to.
>
> **The agents never do arithmetic.** They state lever preferences — a loan count, a rate. Every
> number you're about to see came out of a sandboxed expression, not a language model.
>
> **Constraints are checked, not weighted.** A portfolio that breaches the 5% default cap isn't
> a low score. It's invalid, and the agent who owns that limit is the one who says so.

### 2:00–5:00 — Trace demo (the three minutes that matter)

**Beat 1 — Search** (~25s).
> Before anyone speaks, we search the lever space — twenty thousand portfolios — and keep only
> the ones that satisfy all eight constraints. Plus the obvious greedy answer, kept
> deliberately.

**Beat 2 — The greedy answer is illegal** (~35s). *Slow down here.*
> The profit-maximizing portfolio is 450 manufacturers and 250 SMEs — the two highest-margin
> segments. It's also **infeasible**: manufacturers end up at 73% of deployed capital against a
> 70% concentration limit. That's not our opinion, it's the constraint expression, and Credit
> Risk raises it as a blocking objection citing the limit by id.
>
> Most analyses would have shipped that portfolio.

**Beat 3 — The feasible optimum, and why it's still not the answer** (~60s). *The money shot.*
> The best feasible portfolio is roughly 426 manufacturers, 274 SMEs, at the 19% cap.
> **Zero retail shops** — the largest demand pool, 1,500 of the smallest businesses, untouched.
>
> Marketing objects: that's the growth base, and half the acquisition budget goes unspent.
> Compliance objects harder: we'd be launching a small-business lender that serves no small
> shops. Credit Risk defends — retail carries the 5% default rate, and it's what pushed the
> greedy portfolio over the line in the first place.
>
> Finance revises: a retail tranche is affordable if it's priced and capped. That revision is
> in the trace, timestamped, marked `revised`.

**Beat 4 — Decide** (~50s).
> The CEO's brief says, in the organizers' own words, *do not approve a strategy solely because
> it maximizes short-term revenue.*
>
> So the decision isn't the top-ranked row. Here's the chosen portfolio, the eight required
> sections — segment, product terms, approval policy, budget allocation, risk limits,
> go-to-market, sequence, measurable outcomes — the rejected alternative with the constraint it
> broke, and three KPIs with baselines.
>
> The override is recorded and justified. The score is decision *support*.

**Beat 5 — Failure** (~20s, if the clock allows).
> Kill Credit Risk mid-run. The board still decides, on its last validated position, with
> confidence dropped and the degradation flagged on the output.

### 5:00–6:00 — Surprise, then the closer

> The shock: [read verbatim].
>
> Note what changed isn't only a number — it moved a **limit**: the risk committee dropped the
> default cap from 5% to 5.5%. Our system patches constraints, not just values.
>
> These variables feed Credit Risk, Finance and Research, so those three re-ran.
> **Marketing did not re-run** — the channel economics and the acquisition budget are untouched,
> so its position stands. We re-open exactly what the news invalidated.
>
> Here are the assumptions that are no longer valid — the test case asks for that by name — and
> the revised decision.

**The closer (~20s):**
> One last thing. We prepared Theme A. *[open Theme C — GPU capacity allocation]* Same code,
> nothing changed, a different roster from the case file — a full board decision on a theme we
> didn't pick.
>
> We didn't build a solution to your test case. We built a board that runs all fifteen.

---

## Judge Q&A prep

§7: judges may ask to *change one input, open an agent instruction, inspect a trace, or explain
how a result was generated.* Have all four ready as **actions**, not answers.

| Question | Do this |
|---|---|
| "Change one input." | Streamlit sidebar → move a weight or a variable → rerun. Under 60s. Know the fastest one in advance. |
| "How was that number generated?" | Open the metric expression, point at the variable keys, show the sandbox. |
| "Show me an agent's instruction." | Open the Credit Risk mandate and its derived fact slice side by side. |
| "Is this really six agents?" | Show the `visible_to` slices — different input sets — then the objection where one agent's output *changed* another's. One prompt cannot disagree with itself and revise. |
| **"An LLM wrote your business model. Isn't that a hallucinated spreadsheet?"** | Three layers: (1) the validator proves every formula and constraint parses, resolves and computes before the board sees it; (2) every value not in the brief is tagged `source: "assumption"` with a note, visible in the trace — and in this theme that list is nearly empty, because the brief supplies everything; (3) we read the pack as a team and checked it against the brief's eight constraints. **Show the assumptions list.** Sharpest question they can ask — rehearse it. |
| "You let an LLM write executable expressions?" | Whitelisted AST nodes, no `__builtins__`, no attribute access, no imports, unknown names rejected pre-compile. Show the hostile-input tests. |
| **"Why do you need agents if you have a solver?"** | *"The solver finds what's feasible. It cannot see that a lender serving zero small shops is a conduct problem, or that your own brief says not to maximize short-term revenue. Those moved the decision, and they came from Compliance and the CEO — not from the search."* |
| "How novel is this really?" | Straight: *"Portfolio optimization under constraints is textbook. We're not claiming a new algorithm. What we built is the decision layer on top — constraint ownership, cross-functional objection, selective re-planning — and it runs every theme in your pack."* Never oversell. |
| "What if an agent hallucinates a number?" | It can't affect the outcome — agents emit levers, the sandbox computes metrics, and agents are forbidden to write currency figures. Show the schema. |
| "What about fair lending / discrimination?" | The theme's guardrails are injected into every prompt and checked after. We segment on business type, loan size, and default history — never on any protected characteristic. **Have the guardrail block on screen.** |
| "What if the API dies?" | The ladder: retry → fallback model → last-good cache → stub with confidence penalty. Or run `--fail credit_risk` live. |
| "How much did you build today?" | Point at the README declaration section. Name the pre-built plumbing, name what was authored today, mention the Rules Desk clarification. **Rehearse this** — hesitating looks worse than the truth. |
| "Would this work at a real lender?" | *"The constraint logic is exactly how a risk committee works. The elasticity between price and volume is the one thing we'd fit from real origination data rather than take from the brief."* |

### Never say
- Any unverified external figure — the group-chat numbers stay off the slides
- "Nobody is doing this" — false, and a knowledgeable judge will burn us
- "The score picked the portfolio" — undersells the entire design
- Anything implying a real regulatory position or real financial advice — the theme forbids it

---

## Demo safety

- Golden run on disk. `replay` verified **with wifi off** before we walk in.
- Screen recording of a clean baseline + surprise as last resort.
- Live run only if a full run reliably completes in <90s; otherwise replay and say so — a saved
  trace is explicitly permitted (§7).
- **The closer needs a pre-validated Theme C pack.** If intake has to run live and stumbles,
  we've closed on a failure. Have the JSON ready; show the run, not the generation.
- Laptop on power. Notifications off. Terminal font up. Browser zoom set.
- One person drives, one person talks. Never the same person.
