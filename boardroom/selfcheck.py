"""Run every module's self-check plus an end-to-end offline pipeline pass.

    python -m boardroom.selfcheck

Exercises the whole deterministic system with the stub LLM — no API key, no network.
The brief->pack intake half and real-model prose are covered by `python -m boardroom.drill`
when a provider key is set.
"""

from __future__ import annotations

import io
import time
import traceback
from contextlib import redirect_stdout

MODULES = [
    "boardroom.state",
    "boardroom.calculator",
    "boardroom.oracles",
    "boardroom.generate",
    "boardroom.scoring",
    "boardroom.llm",
    "boardroom.agents",
    "boardroom.engine",
    "boardroom.intake",
    "boardroom.cli",
]


def _run_demo(name: str) -> tuple[bool, str, float]:
    mod = __import__(name, fromlist=["demo"])
    t0 = time.perf_counter()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            mod.demo()
        return True, buf.getvalue().strip().splitlines()[-1], time.perf_counter() - t0
    except Exception:
        return False, traceback.format_exc(), time.perf_counter() - t0


def _e2e() -> tuple[bool, str, float]:
    """Baseline run -> surprise -> replay round-trip, all stub."""
    import json
    from pathlib import Path

    from boardroom.cli import render_text
    from boardroom.engine import adapt, run, save_run, validate
    from boardroom.llm import LLM
    from boardroom.state import BoardroomState

    t0 = time.perf_counter()
    root = Path(__file__).resolve().parent.parent
    pack = json.loads((root / "cases" / "themeA_tc1.json").read_text("utf-8"))

    base = run(pack, llm=LLM(mode="stub"))
    assert validate(base.decision, pack) == []
    assert [s for s in base.strategies if s.verdict == "selected"]
    p1 = save_run(base, "selfcheck_base")

    delta = json.loads((root / "briefs" / "themeA_tc2.facts.json").read_text("utf-8"))
    surp = adapt(base, facts=delta, llm=LLM(mode="stub"))
    assert surp.parent_run == base.run_id
    assert validate(surp.decision, surp.pack) == []
    assert surp.reran and surp.unchanged and surp.invalidated_assumptions
    p2 = save_run(surp, "selfcheck_surprise")

    reloaded = BoardroomState.model_validate_json(p2.read_text("utf-8"))
    txt = render_text(reloaded)
    assert "CEO DECISION" in txt and "surprise on" in txt

    dt = time.perf_counter() - t0
    return True, (f"baseline={base.decision.chosen} surprise={surp.decision.chosen} "
                  f"reran={surp.reran} ({p1.name}, {p2.name})"), dt


def main() -> int:
    print("=" * 72)
    ok = True
    for name in MODULES:
        passed, detail, dt = _run_demo(name)
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {name:<24} {dt:5.2f}s  {detail if passed else ''}")
        if not passed:
            ok = False
            print(detail)

    passed, detail, dt = _e2e()
    print(f"[{'PASS' if passed else 'FAIL'}] {'end-to-end (stub)':<24} {dt:5.2f}s  {detail}")
    ok = ok and passed

    print("=" * 72)
    print("ALL GREEN" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
