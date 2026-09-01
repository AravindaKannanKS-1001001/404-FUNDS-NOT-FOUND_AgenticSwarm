
--- CHALLENGE ROUND ---
The other departments recommended:
$digest

Return an `objections` array. Rules:
- If a candidate violates a hard constraint you own, that is a "blocking" objection —
  set `cites_constraint` to the constraint id.
- A recommendation that materially hurts your mandate is a "material" objection.
- If you genuinely have no material objection, return exactly one with severity "minor"
  stating what would have to change for you to object.
- Never invent a disagreement you do not hold.
Each objection needs `from_agent` (you), `against` (an agent id or strategy id),
`severity`, `claim`, `evidence`.
