"""The Phase 0 drill — run every case we have through the full pipeline, zero code edits.

    python -m boardroom.drill            # runs cases/*.json + *.facts.json surprises
    python -m boardroom.drill --intake   # also brief -> pack -> board (needs a provider key)

Pass condition: every case produces a valid CEO decision. Any case that forces a code
change is a hole in the abstraction.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from boardroom.engine import adapt, run, validate
from boardroom.intake import validate_pack
from boardroom.llm import LLM
from boardroom.oracles import ORACLES, verify

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"
BRIEFS = ROOT / "briefs"


def _row(name: str, ok: bool, dt: float, detail: str) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name:<26} {dt:5.2f}s  {detail}")


def drill(do_intake: bool = False) -> int:
    llm = LLM(mode="stub")
    all_ok = True

    for pack_path in sorted(CASES.glob("*.json")):
        cid = pack_path.stem
        t0 = time.perf_counter()
        try:
            pack = json.loads(pack_path.read_text("utf-8"))
            verrs = validate_pack(pack)
            assert not verrs, f"pack invalid: {verrs}"
            state = run(pack, llm=llm)
            derrs = validate(state.decision, pack)
            assert not derrs, f"decision invalid: {derrs}"
            sel = [s for s in state.strategies if s.verdict == "selected"]
            feas = [s for s in state.strategies if not s.violations]
            assert sel or not feas, "feasible candidates exist but none selected"
            if cid in ORACLES:
                verify(cid)
            chosen = state.decision.chosen or "(none feasible)"
            _row(cid, True, time.perf_counter() - t0,
                 f"chose {chosen}, {len(feas)} feasible, oracle "
                 f"{'ok' if cid in ORACLES else 'n/a'}")
        except Exception as e:  # noqa: BLE001 - drill reports, doesn't crash
            all_ok = False
            _row(cid, False, time.perf_counter() - t0, repr(e))

    for facts_path in sorted(BRIEFS.glob("*.facts.json")):
        name = facts_path.name
        base_id = name.split(".")[0].rsplit("_", 1)[0] + "_tc1"
        base_pack = CASES / f"{base_id}.json"
        t0 = time.perf_counter()
        try:
            assert base_pack.exists(), f"no baseline pack {base_pack.name}"
            base = run(json.loads(base_pack.read_text("utf-8")), llm=llm)
            surp = adapt(base, facts=json.loads(facts_path.read_text("utf-8")), llm=llm)
            assert validate(surp.decision, surp.pack) == []
            assert surp.reran and surp.invalidated_assumptions
            _row(name, True, time.perf_counter() - t0,
                 f"re-ran {surp.reran}, skipped {[u['agent'] for u in surp.unchanged]}")
        except Exception as e:  # noqa: BLE001
            all_ok = False
            _row(name, False, time.perf_counter() - t0, repr(e))

    if do_intake:
        real = LLM()
        if real.mode == "stub":
            print("\n--intake skipped: no GOOGLE_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY")
        else:
            from boardroom.intake import intake
            for brief in sorted(BRIEFS.glob("*.txt")):
                t0 = time.perf_counter()
                try:
                    pack = intake(brief, llm=real)
                    state = run(pack, llm=real)
                    assert validate(state.decision, pack) == []
                    _row(f"intake:{brief.stem}", True, time.perf_counter() - t0,
                         f"{len(pack['roster'])} agents, chose {state.decision.chosen}")
                except Exception as e:  # noqa: BLE001
                    all_ok = False
                    _row(f"intake:{brief.stem}", False, time.perf_counter() - t0, repr(e))

    print("=" * 72)
    print("DRILL GREEN" if all_ok else "DRILL FAILURES ABOVE")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(drill("--intake" in sys.argv))
