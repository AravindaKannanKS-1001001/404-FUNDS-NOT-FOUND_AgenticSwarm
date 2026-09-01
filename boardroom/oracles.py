"""Hand-computed reference points for the TC1 packs.

These are the check the generator (Step 4) and the drill (Step 12) verify against.
The figures are worked out by hand in docs/THEMES.md; if the generator disagrees,
one of the two is wrong and that reconciliation is the point of the exercise.

NOTE (2026-09-01): the original THEMES §3.3 oracle for themeA_tc1 was arithmetically
wrong - it maximised per-loan contribution subject to the 70% concentration cap but
ignored that INR 30 crore of capital only funds ~INR 27 crore of loans after the
INR 3 crore reserve. 426 mfg + 274 SME needs INR 54.78 crore of capital that does
not exist. Corrected figures below; THEMES.md updated to match.
"""

from __future__ import annotations

import json
from pathlib import Path

from boardroom.calculator import check, compute

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"

ORACLES: dict[str, dict] = {
    "themeA_tc1": {
        # Feasible optimum. rate at the 0.19 ceiling; SME filled to exactly the 70%
        # concentration cap; the rest in manufacturers; retail excluded (worst return
        # per rupee of scarce capital). Liquidity, concentration and rate all bind.
        "optimum": {
            "levers": {"n_retail": 0, "n_sme": 315, "n_mfg": 90, "rate": 0.19},
            "net_income": 6_592_500.0,
            "deployed": 270_000_000.0,
            "tol": 0.03,  # a lattice search lands a hair inside the binding faces
        },
        # The naive answer: fill the 700-loan cap with the two highest-margin
        # segments. Asks to lend INR 55.5 crore against INR 30 crore of capital and
        # puts manufacturers at ~73% of the book.
        "greedy_infeasible": {
            "levers": {"n_retail": 0, "n_sme": 250, "n_mfg": 450, "rate": 0.19},
            "must_violate": ["liquidity", "concentration"],
        },
    },
    "themeC_tc1": {
        # AI to demand (best margin/hour, 7,500), gaming at its committed minimum, the
        # remaining hours to edge, all inside the 1,200h buffer. Capacity binds.
        "optimum": {
            "levers": {"n_ai": 2500, "n_gaming": 2000, "n_edge": 1266},
            "net_income": 155_288_000.0,   # contribution_margin; key remapped below
            "objective_key": "contribution_margin",
            "tol": 0.02,
        },
        "greedy_infeasible": {
            "levers": {"n_ai": 2500, "n_gaming": 6000, "n_edge": 3500},
            "must_violate": ["capacity"],
        },
    },
}


def load_pack(case_id: str) -> dict:
    return json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


def base_ns(pack: dict) -> dict:
    return {v["key"]: v["value"] for v in pack["variables"]}


def evaluate(pack: dict, levers: dict) -> tuple[dict, list[dict]]:
    ns = {**base_ns(pack), **levers}
    metrics = compute(pack["metrics"], ns)
    violations = check(pack["constraints"], {**ns, **metrics})
    return metrics, violations


def verify(case_id: str) -> None:
    """Assert the pack reproduces its hand-computed oracle. Raises AssertionError."""
    pack = load_pack(case_id)
    o = ORACLES[case_id]
    obj_key = o["optimum"].get("objective_key", pack["objective"])

    opt = o["optimum"]
    m, v = evaluate(pack, opt["levers"])
    assert v == [], f"{case_id}: oracle optimum is infeasible: {[c['id'] for c in v]}"
    target = opt["net_income"]
    lo, hi = target * (1 - opt["tol"]), target * (1 + opt["tol"])
    assert lo <= m[obj_key] <= hi, (
        f"{case_id}: {obj_key} {m[obj_key]:,.0f} outside "
        f"[{lo:,.0f}, {hi:,.0f}] of oracle {target:,.0f}"
    )
    if "deployed" in opt:
        assert abs(m["deployed"] - opt["deployed"]) < 1e6, m["deployed"]

    g = o["greedy_infeasible"]
    _, gv = evaluate(pack, g["levers"])
    got = {c["id"] for c in gv}
    for cid in g["must_violate"]:
        assert cid in got, f"{case_id}: greedy seed should violate {cid}; violates {got}"


def demo() -> None:
    """Acceptance check - HANDOVER Step 3."""
    pack = load_pack("themeA_tc1")

    # schema sanity: every visible_to / owner references a real roster id
    roster_ids = {r["id"] for r in pack["roster"]}
    for var in pack["variables"]:
        bad = set(var["visible_to"]) - roster_ids
        assert not bad, f"variable {var['key']}: visible_to has non-roster {bad}"
    for c in pack["constraints"]:
        assert c["owner"] in roster_ids, f"constraint {c['id']}: owner {c['owner']!r} not on roster"
    for role, ref in pack["score_inputs"].items():
        if ref.startswith("signal:"):
            sig = ref.split(":", 1)[1]
            declared = {s for r in pack["roster"] for s in r["signals"]}
            assert sig in declared, f"score_inputs[{role}] wants undeclared signal {sig!r}"
        else:
            key = ref.split(":", 1)[-1]
            assert key in pack["metrics"], f"score_inputs[{role}] wants unknown metric {key!r}"
    assert abs(sum(pack["weights"].values()) - 1.0) < 0.01

    # every metric and constraint expression evaluates on every seed
    for seed in pack["seed_strategies"]:
        m, v = evaluate(pack, seed["levers"])
        assert set(m) == set(pack["metrics"]), seed["id"]
        print(f"  seed {seed['id']:<10} net={m['net_income']:>14,.0f}  "
              f"deployed={m['deployed']:>14,.0f}  "
              f"violations={[c['id'] for c in v] or 'none'}")

    # the corrected oracle
    verify("themeA_tc1")

    m, v = evaluate(pack, ORACLES["themeA_tc1"]["optimum"]["levers"])
    print(f"\n  oracle optimum (0 / 315 / 90 @ 0.19):")
    print(f"    net_income          {m['net_income']:>16,.2f}")
    print(f"    deployed            {m['deployed']:>16,.2f}")
    print(f"    portfolio_default   {m['portfolio_default_pct']:>16.4f}")
    print(f"    max_segment_share   {m['max_segment_share']:>16.4f}")
    print(f"    undeployed_capital  {m['undeployed_capital']:>16,.2f}")
    print(f"    violations          {[c['id'] for c in v] or 'none'}")

    print("\noracles.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
