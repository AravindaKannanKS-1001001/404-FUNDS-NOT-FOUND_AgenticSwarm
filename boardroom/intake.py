"""Intake — raw brief to a validated case pack.

A pre-board tool, not a judged agent (rulebook §2 exempts deterministic tooling). One LLM
call builds the pack; ``validate_pack`` then proves it computes before any board member
sees it. If validation fails, one repair retry with the error list; failing that, a human
patches the JSON.

``validate_pack`` is the load-bearing half and runs with no LLM — it is the Phase 1 gate
and the Step 12 drill check.
"""

from __future__ import annotations

import json
from pathlib import Path
from string import Template

from boardroom.calculator import _compile, check, compute
from boardroom.llm import LLM

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
CASES = Path(__file__).resolve().parent.parent / "cases"
BRIEFS = Path(__file__).resolve().parent.parent / "briefs"

_REQUIRED_KEYS = (
    "case_id", "company", "problem", "decision_question", "roster", "ceo", "guardrails",
    "required_decision_fields", "variables", "levers", "metrics", "constraints",
    "direction", "objective", "score_inputs", "weights", "seed_strategies",
)


def validate_pack(pack: dict) -> list[str]:
    """Deterministic. Returns a list of human-readable problems ([] == good)."""
    errs: list[str] = []

    for key in _REQUIRED_KEYS:
        if key not in pack:
            errs.append(f"missing top-level key: {key}")
    if errs:
        return errs  # nothing else is safe to check

    roster = pack["roster"]
    ids = [r.get("id") for r in roster]
    idset = set(ids)
    if not roster:
        errs.append("roster is empty")
    if len(ids) != len(idset):
        errs.append("duplicate roster ids")
    if not pack["ceo"].get("objective"):
        errs.append("ceo.objective is empty")
    for f in ("guardrails", "required_decision_fields"):
        if not pack[f]:
            errs.append(f"{f} is empty")

    ns0: dict = {}
    for i, v in enumerate(pack["variables"]):
        for k in ("key", "value", "source", "visible_to"):
            if k not in v:
                errs.append(f"variable #{i} missing '{k}'")
        if "key" in v and "value" in v:
            ns0[v["key"]] = v["value"]
        bad = set(v.get("visible_to", [])) - idset
        if bad:
            errs.append(f"variable {v.get('key')!r}: visible_to not on roster: {sorted(bad)}")
        if v.get("source") not in ("case_pack", "assumption"):
            errs.append(f"variable {v.get('key')!r}: source must be case_pack or assumption")

    for lv in pack["levers"]:
        for k in ("key", "min", "max", "owner"):
            if k not in lv:
                errs.append(f"lever {lv.get('key')!r} missing '{k}'")
        if lv.get("owner") not in idset:
            errs.append(f"lever {lv.get('key')!r}: owner {lv.get('owner')!r} not on roster")

    for name, expr in pack["metrics"].items():
        try:
            _compile(expr)
        except ValueError as e:
            errs.append(f"metric {name}: {e}")
    for c in pack["constraints"]:
        if "expr" not in c or "id" not in c:
            errs.append(f"constraint {c!r} missing id/expr")
            continue
        try:
            _compile(c["expr"])
        except ValueError as e:
            errs.append(f"constraint {c['id']}: {e}")
        if c.get("owner") not in idset:
            errs.append(f"constraint {c['id']}: owner {c.get('owner')!r} not on roster")

    if len(pack["metrics"]) < 3:
        errs.append("need at least 3 metrics")
    if len(pack["constraints"]) < 1:
        errs.append("need at least 1 constraint")
    if len(pack["seed_strategies"]) < 2:
        errs.append("need at least 2 seed strategies")

    for s in pack["seed_strategies"]:
        try:
            m = compute(pack["metrics"], {**ns0, **s.get("levers", {})})
            check(pack["constraints"], {**ns0, **s.get("levers", {}), **m})
        except (ValueError, KeyError) as e:
            errs.append(f"seed {s.get('id')!r} does not evaluate: {e}")

    metrics = set(pack["metrics"])
    signals = {sig for r in roster for sig in r.get("signals", [])}
    for role, ref in pack["score_inputs"].items():
        target = ref.split(":", 1)[-1]
        if ref.startswith("signal:"):
            if target not in signals:
                errs.append(f"score_inputs[{role}]: signal {target!r} not declared on any roster agent")
        elif target not in metrics:
            errs.append(f"score_inputs[{role}]: unknown metric {target!r}")
    w = pack["weights"]
    if abs(sum(w.values()) - 1.0) > 0.01:
        errs.append(f"weights sum to {sum(w.values()):.3f}, must be 1.0")
    if pack["objective"] not in metrics:
        errs.append(f"objective {pack['objective']!r} is not a metric")

    return errs


def intake(brief: str | Path, llm: LLM | None = None, out: str | Path | None = None) -> dict:
    """Brief -> validated pack dict. Raises RuntimeError if it cannot be made valid."""
    text = Path(brief).read_text(encoding="utf-8") if Path(str(brief)).exists() else str(brief)
    llm = llm or LLM()
    prompt = Template((PROMPTS / "_intake.md").read_text(encoding="utf-8")).substitute(brief=text)

    pack = llm.call_json("You output only a single JSON object.", prompt)
    errs = validate_pack(pack)
    if errs:
        repair = prompt + "\n\nYour previous pack failed validation:\n" + "\n".join(
            f"- {e}" for e in errs) + "\nReturn a corrected JSON object."
        pack = llm.call_json("You output only a single JSON object.", repair)
        errs = validate_pack(pack)
    if errs:
        raise RuntimeError("intake could not produce a valid pack:\n" + "\n".join(errs))

    if out:
        Path(out).write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    return pack


def demo() -> None:
    """Acceptance check - HANDOVER Step 9: the validator accepts the good pack and gives
    readable errors on broken ones. (The brief->pack->oracle round-trip needs a real LLM
    and is exercised by the smoke test when a key is present.)"""
    import copy

    good = json.loads((CASES / "themeA_tc1.json").read_text(encoding="utf-8"))
    assert validate_pack(good) == [], validate_pack(good)

    def breaks(mut, expect: str):
        p = copy.deepcopy(good)
        mut(p)
        got = validate_pack(p)
        assert any(expect in e for e in got), f"expected {expect!r} in {got}"
        return got

    breaks(lambda p: p["variables"][0]["visible_to"].append("ghost"),
           "not on roster")
    breaks(lambda p: p["metrics"].update(net_income="deployed * mystery_rate"),
           "unknown name 'mystery_rate'")
    breaks(lambda p: p["metrics"].update(bad="__import__('os')"),
           "disallowed")
    breaks(lambda p: p["weights"].update(value=0.9),
           "weights sum")
    breaks(lambda p: p["constraints"].__setitem__(0, {**p["constraints"][0], "owner": "nobody"}),
           "not on roster")
    breaks(lambda p: p.pop("objective"),
           "missing top-level key: objective")
    breaks(lambda p: p["seed_strategies"][0]["levers"].update(n_sme="lots"),
           "does not evaluate")

    print("  good pack: valid")
    print("  broken packs: all produced targeted errors")
    print("intake.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
