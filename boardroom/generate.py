"""Candidate generator — bounded random search over the lever space.

These test cases are constrained optimisation problems with near-exact optima a judge
can check with a calculator (docs/THEMES.md §1.3). Letting an LLM pick round numbers
loses Business Value, so we search: sample levers, compute metrics, keep the feasible
ones, rank on the pack objective, hand the board a diverse top-k plus the seed corner
strategies (kept even when infeasible — a real rejected alternative with a named breach).

    candidates(pack) -> list[Strategy]   (search picks first, then seeds)

ponytail: random search, not an LP solver. Fine for <=6 smooth levers, which is every
published case. Swap for scipy.optimize.linprog only if a pack shows up with a nasty
integer space.
"""

from __future__ import annotations

import random

from boardroom.calculator import check, compute
from boardroom.state import Strategy, Violation


def _sample(lever: dict, rng: random.Random) -> float:
    lo, hi, step = lever["min"], lever["max"], lever.get("step") or 0
    if step > 0:
        steps = int(round((hi - lo) / step))
        return round(lo + rng.randint(0, steps) * step, 10)
    return rng.uniform(lo, hi)


def _violations(pack: dict, ns: dict) -> list[Violation]:
    return [
        Violation(constraint_id=c["id"], label=c["label"], owner=c["owner"], margin=c["margin"])
        for c in check(pack["constraints"], ns)
    ]


def _norm(levers: dict, pack: dict) -> list[float]:
    out = []
    for lv in pack["levers"]:
        lo, hi = lv["min"], lv["max"]
        span = (hi - lo) or 1.0
        out.append((levers[lv["key"]] - lo) / span)
    return out


def _dist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _diversify(ranked: list, pack: dict, k: int, min_dist: float = 0.05) -> list:
    """Greedily drop candidates that sit within min_dist (normalised L2) of one already
    picked, so the board argues over genuinely different portfolios, not rounding noise."""
    picked: list = []
    picked_norm: list = []
    for row in ranked:
        nl = _norm(row[1], pack)
        if all(_dist(nl, pn) >= min_dist for pn in picked_norm):
            picked.append(row)
            picked_norm.append(nl)
        if len(picked) >= k:
            break
    return picked


def _evaluate(pack: dict, levers: dict, ns0: dict) -> tuple[dict, list[Violation]]:
    ns = {**ns0, **levers}
    metrics = compute(pack["metrics"], ns)
    return metrics, _violations(pack, {**ns, **metrics})


def _obj(pack: dict, levers: dict, ns0: dict, key: str) -> float | None:
    """Objective value if this lever vector is feasible, else None."""
    try:
        ns = {**ns0, **levers}
        metrics = compute(pack["metrics"], ns)
    except ValueError:
        return None
    if check(pack["constraints"], {**ns, **metrics}):
        return None
    return metrics[key]


def _snap(lever: dict, value: float) -> float:
    value = min(lever["max"], max(lever["min"], value))
    step = lever.get("step") or 0
    if step > 0:
        value = round(round(value / step) * step, 10)
    return value


def _climb(pack: dict, levers: dict, ns0: dict, key: str, maximize: bool) -> tuple[dict, float | None]:
    """Compass search from one feasible point to the nearby constrained vertex.
    Coarse steps first, then native step size — this is what actually reaches the
    optimum; random sampling only finds the basin."""
    better = (lambda a, b: a > b) if maximize else (lambda a, b: a < b)
    best = _obj(pack, levers, ns0, key)
    if best is None:
        return levers, None
    for scale in (64, 16, 4, 1):
        moved = True
        while moved:
            moved = False
            # single-axis probes, then opposing pairs (to slide along a binding face,
            # e.g. trading capital between two segments while deployed stays fixed)
            probes = [((lv["key"], d),) for lv in pack["levers"] for d in (1, -1)]
            probes += [
                ((a["key"], da), (b["key"], db))
                for i, a in enumerate(pack["levers"]) for b in pack["levers"][i + 1:]
                for da, db in ((1, -1), (-1, 1))
            ]
            for probe in probes:
                cand = dict(levers)
                changed = False
                for lkey, sign in probe:
                    lv = next(x for x in pack["levers"] if x["key"] == lkey)
                    base = lv.get("step") or (lv["max"] - lv["min"]) / 100.0
                    nv = _snap(lv, cand[lkey] + sign * base * scale)
                    changed |= nv != cand[lkey]
                    cand[lkey] = nv
                if not changed:
                    continue
                val = _obj(pack, cand, ns0, key)
                if val is not None and better(val, best):
                    levers, best, moved = cand, val, True
    return levers, best


def _polish(pack: dict, levers: dict, ns0: dict, key: str, maximize: bool,
            rng: random.Random, iters: int = 2500) -> tuple[dict, float | None]:
    """Stochastic finisher — diagonal moves the axis-aligned compass search can't make."""
    better = (lambda a, b: a > b) if maximize else (lambda a, b: a < b)
    best = _obj(pack, levers, ns0, key)
    if best is None:
        return levers, None
    for _ in range(iters):
        cand = dict(levers)
        for lv in pack["levers"]:
            r = rng.random()
            if r < 0.45:
                continue
            if r < 0.6:  # jump to a bound — lets the search zero out a weak lever
                cand[lv["key"]] = rng.choice((lv["min"], lv["max"]))
            else:
                base = lv.get("step") or (lv["max"] - lv["min"]) / 100.0
                cand[lv["key"]] = _snap(lv, cand[lv["key"]]
                                        + rng.choice((-1, 1)) * base * rng.choice((1, 2, 4, 8, 16)))
        val = _obj(pack, cand, ns0, key)
        if val is not None and better(val, best):
            levers, best = cand, val
    return levers, best


def seed_strategies(pack: dict) -> list[Strategy]:
    ns0 = {v["key"]: v["value"] for v in pack["variables"]}
    out = []
    for s in pack.get("seed_strategies", []):
        try:
            metrics, viols = _evaluate(pack, s["levers"], ns0)
        except ValueError:
            metrics, viols = {}, []
        out.append(Strategy(id=s["id"], name=s["name"], levers=dict(s["levers"]),
                            metrics=metrics, violations=viols, origin="seed"))
    return out


def candidates(pack: dict, n_samples: int = 8000, k: int = 5, seed: int = 1) -> list[Strategy]:
    # 8k random samples locate the feasible basin; _climb + _polish reach the vertex.
    # Pure-Python AST eval costs ~115us/sample, so more samples buy little over search.
    rng = random.Random(seed)
    ns0 = {v["key"]: v["value"] for v in pack["variables"]}
    obj = pack["objective"]
    maximize = pack["direction"].get(obj, "max") == "max"

    feasible: list = []
    for _ in range(n_samples):
        levers = {lv["key"]: _sample(lv, rng) for lv in pack["levers"]}
        try:
            metrics = compute(pack["metrics"], {**ns0, **levers})
        except ValueError:
            continue
        if check(pack["constraints"], {**ns0, **levers, **metrics}):
            continue
        feasible.append((metrics[obj], levers, metrics))

    feasible.sort(key=lambda t: t[0], reverse=maximize)

    # refine the best random points (and any feasible seed) toward their local vertex.
    # compass search is cheap so run it broadly; the stochastic polish is the costly
    # part so only finish the few best.
    starts = [row[1] for row in feasible[:10]]
    starts += [s["levers"] for s in pack.get("seed_strategies", [])]
    climbed: list = []
    for start in starts:
        levers, val = _climb(pack, start, ns0, obj, maximize)
        if val is not None:
            climbed.append((val, levers))
    climbed.sort(key=lambda t: t[0], reverse=maximize)
    for val, levers in climbed[:3]:
        for _ in range(3):  # climb <-> polish until it stops improving
            levers, v = _climb(pack, levers, ns0, obj, maximize)
            levers, v2 = _polish(pack, levers, ns0, obj, maximize, rng, iters=1200)
            if v2 is None or (v is not None and abs(v2 - v) < max(abs(v), 1) * 1e-4):
                val = v2 if v2 is not None else v
                break
            val = v2
        climbed.append((val, levers))
    for val, levers in climbed:
        feasible.append((val, levers, compute(pack["metrics"], {**ns0, **levers})))

    feasible.sort(key=lambda t: t[0], reverse=maximize)
    picked = _diversify(feasible, pack, k)
    searched = [
        Strategy(id=f"G{i + 1}", name=f"Search optimum {i + 1}", levers=lv,
                 metrics=m, violations=[], origin="search")
        for i, (_, lv, m) in enumerate(picked)
    ]
    return searched + seed_strategies(pack)


def demo() -> None:
    """Acceptance check - HANDOVER Step 4."""
    import time

    from boardroom.oracles import ORACLES, load_pack, verify

    pack = load_pack("themeA_tc1")
    t0 = time.perf_counter()
    strats = candidates(pack, k=5)
    dt = time.perf_counter() - t0

    searched = [s for s in strats if s.origin == "search"]
    seeds = [s for s in strats if s.origin == "seed"]
    assert dt < 2.5, f"candidate search took {dt:.2f}s (target <2s)"
    assert searched, "no feasible candidate found"

    top = searched[0]
    oracle_net = ORACLES["themeA_tc1"]["optimum"]["net_income"]
    for s in searched:
        print(f"  {s.id:<4} net={s.metrics['net_income']:>13,.0f}  "
              f"retail={s.levers['n_retail']:>4.0f} sme={s.levers['n_sme']:>4.0f} "
              f"mfg={s.levers['n_mfg']:>4.0f} rate={s.levers['rate']:.3f}")
    for s in seeds:
        print(f"  {s.id:<10} net={s.metrics.get('net_income', float('nan')):>13,.0f}  "
              f"violations={[v.constraint_id for v in s.violations] or 'none'}")

    assert top.metrics["net_income"] >= oracle_net * 0.97, (
        f"top candidate {top.metrics['net_income']:,.0f} below 97% of oracle {oracle_net:,.0f}"
    )
    assert top.levers["n_retail"] <= 30, f"optimum should exclude retail, got {top.levers['n_retail']}"

    seed_ids = {s.id for s in seeds}
    assert {"S_retail", "S_greedy"} <= seed_ids, seed_ids
    greedy = next(s for s in seeds if s.id == "S_greedy")
    assert {v.constraint_id for v in greedy.violations} >= {"liquidity", "concentration"}, greedy.violations

    verify("themeA_tc1")  # generator agrees with the hand oracle
    gap = 1 - top.metrics["net_income"] / oracle_net
    print(f"\n  search in {dt:.2f}s | top {gap * 100:.1f}% below LP optimum | "
          f"{len(searched)} optima + {len(seeds)} seeds")
    print("generate.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
