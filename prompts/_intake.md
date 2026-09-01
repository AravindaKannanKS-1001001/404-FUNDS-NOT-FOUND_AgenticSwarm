You are a decision-modelling analyst. Turn the business brief below into a single JSON
"case pack" that a downstream boardroom engine can run. Output ONLY the JSON object.

EXTRACTION, NOT INVENTION. The brief states every fact the decision needs. Copy values
from it. If the metrics you write genuinely need a value the brief does not give, add it
as a variable with "source": "assumption" and a "note" explaining the gap — never as
"case_pack", and never silently. Prefer leaving a metric out over inventing an input.

The JSON must have exactly these keys:

- case_id            : short slug
- company            : the company name from the brief
- theme              : the theme name if stated, else ""
- problem            : one paragraph restating the situation
- decision_question  : the single question the board must answer (quote the brief)
- roster             : array of the MANDATORY agents except the CEO. Each:
                       { "id": snake_case, "title": ..., "mandate": one sentence,
                         "signals": 1-2 snake_case 0..1 signal names it owns }
- ceo                : { "title": "CEO Agent", "objective": quote the brief's balance sentence }
- guardrails         : array of the brief's prohibition sentences, verbatim
- required_decision_fields : array of snake_case keys, one per item the brief says the
                       final decision "must specify"
- variables          : array of { key, value, unit, source: "case_pack"|"assumption",
                       visible_to: [roster ids], note }. Put every number the metrics or
                       constraints reference here, including the constraint limits
                       (e.g. default_limit, rate_limit). visible_to = the agents whose
                       mandate covers that fact.
- levers             : the decision variables, array of
                       { key, min, max, step, owner: roster id }
- metrics            : { name: expression-string }. Expressions may use variable keys,
                       lever keys, earlier metric names and: min max abs round exp sqrt log.
                       No other names, no attributes, no calls.
- constraints        : array of { id, expr: "<= / >= / < / >" string, label: the brief's
                       sentence, owner: the roster id whose mandate covers it }
- direction          : { metric_name: "max" | "min" } for the metrics that have a preferred
                       direction
- objective          : the single metric name the search maximises or minimises
- score_inputs       : { "value": ref, "efficiency": ref, "feasibility": ref,
                       "customer": ref, "risk": ref } where ref is "metric:<name>" or
                       "signal:<name>" (signal names must be declared on the roster)
- weights            : { value, efficiency, feasibility, customer, risk } summing to 1.0
- seed_strategies    : 2-3 corner cases as { id, name, levers: {...} }. Include the naive
                       greedy answer even if it will turn out infeasible.

BRIEF:
$brief
