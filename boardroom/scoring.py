"""Weighted strategy score — decision *support*, not the decision.

Five fixed weight slots (value / efficiency / feasibility / customer / risk). The pack
maps each to a metric or to an agent-owned 0-1 signal via ``score_inputs``. Metrics are
min-max normalised across the feasible cohort; agent signals are used as-is.

A strategy with any hard-constraint violation scores 0 — a breach beats every weight.
The board's signals arrive after the deterministic search, so the ranking here can and
does differ from the pure-objective order. That gap is the point: search finds feasible,
the board decides wise.
"""

from __future__ import annotations

from boardroom.state import Strategy


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def normalize(value: float, key: str, direction: dict, cohort: list[float]) -> float:
    """Min-max ``value`` against the cohort; invert if the pack wants this metric small."""
    lo, hi = min(cohort), max(cohort)
    t = 0.5 if hi <= lo else (value - lo) / (hi - lo)
    if direction.get(key) == "min":
        t = 1.0 - t
    return clamp01(t)


def _metric_key(ref: str) -> str:
    return ref.split(":", 1)[1] if ref.startswith("metric:") else ref


def score(strategy: Strategy, signals: dict, pack: dict, cohort: list[Strategy]) -> float:
    if strategy.violations:
        return 0.0
    feasible = [s for s in cohort if not s.violations] or [strategy]
    total = 0.0
    for role, ref in pack["score_inputs"].items():
        w = pack["weights"][role]
        if ref.startswith("signal:"):
            part = clamp01(signals.get(ref.split(":", 1)[1], 0.5))
        else:
            key = _metric_key(ref)
            vals = [s.metrics[key] for s in feasible if key in s.metrics]
            part = normalize(strategy.metrics[key], key, pack["direction"], vals or [0.0])
        total += w * part
    return total


def rank(strategies: list[Strategy], signals: dict, pack: dict) -> list[Strategy]:
    """Score every strategy in place and return them best-first. Infeasible ones keep
    their score 0 and sort to the bottom; ties break on the pack objective."""
    obj, want_max = pack["objective"], pack["direction"].get(pack["objective"], "max") == "max"
    for s in strategies:
        s.score = score(s, signals, pack, strategies)
    return sorted(
        strategies,
        key=lambda s: (s.score, s.metrics.get(obj, 0.0) * (1 if want_max else -1)),
        reverse=True,
    )


def demo() -> None:
    """Acceptance check - HANDOVER Step 5: agent signals reorder the search ranking."""
    from boardroom.generate import candidates
    from boardroom.oracles import load_pack

    pack = load_pack("themeA_tc1")
    strats = candidates(pack, k=5)
    feasible = [s for s in strats if not s.violations]

    neutral = {"liquidity_health": 0.5, "customer_impact": 0.5, "risk_score": 0.5}
    order_neutral = [s.id for s in rank(list(feasible), neutral, pack)]

    # Board signals that reward serving retail and dislike a concentrated book. The
    # search's #1 excludes retail, so this should lift a retail-carrying candidate.
    for s in feasible:
        s.score = score(s, {
            "liquidity_health": 0.5,
            "customer_impact": clamp01(s.levers["n_retail"] / 200.0),
            "risk_score": clamp01(1.0 - s.metrics["max_segment_share"]),
        }, pack, feasible)
    biased_order = [s.id for s in sorted(feasible, key=lambda s: s.score, reverse=True)]

    print(f"  neutral ranking : {order_neutral}")
    print(f"  biased ranking  : {biased_order}")

    assert order_neutral[0] == "G1", order_neutral
    assert biased_order != order_neutral, "signals failed to reorder the ranking"
    assert biased_order[0] != "G1", "board could not overrule the search optimum"

    # a violated strategy always scores 0
    greedy = next(s for s in strats if s.id == "S_greedy")
    assert score(greedy, neutral, pack, strats) == 0.0

    print("scoring.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
