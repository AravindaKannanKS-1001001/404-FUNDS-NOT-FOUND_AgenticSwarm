"""Command line — the system's real interface. Streamlit is only a lens over the same JSON.

    python -m boardroom intake   --brief briefs/themeA_tc1.txt --out cases/themeA_tc1.json
    python -m boardroom run      --case cases/themeA_tc1.json [--stub] [--fail credit_risk]
    python -m boardroom surprise --run runs/X.json (--facts F.json | --brief B.txt)
    python -m boardroom replay   runs/X.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from boardroom.engine import RUNS, adapt, run, save_run, validate
from boardroom.llm import LLM
from boardroom.state import BoardroomState


def _llm(args) -> LLM:
    return LLM(mode="stub") if getattr(args, "stub", False) else LLM()


def render_text(state: BoardroomState) -> str:
    p = state.pack
    out: list[str] = []
    w = out.append
    w(f"=== {p.get('company', '?')} - {state.case_id}  (run {state.run_id}) ===")
    w(f"  {p['decision_question']}")
    if state.parent_run:
        w(f"  surprise on {state.parent_run} | re-ran {state.reran} | "
          f"skipped {[u['agent'] for u in state.unchanged]}")
        for a in state.invalidated_assumptions:
            w(f"    invalidated: {a}")
    w("--- CANDIDATES")
    for s in state.strategies:
        flag = ("SELECTED" if s.verdict == "selected"
                else "rejected" if s.verdict == "rejected" else "viable")
        viol = (" ! " + ",".join(v.constraint_id for v in s.violations)) if s.violations else ""
        levers = " ".join(f"{k}={v:g}" for k, v in s.levers.items())
        w(f"  [{s.id:<10}] {flag:<8} score={s.score:.3f} {levers}{viol}")
    w("--- RECOMMENDATIONS")
    for r in state.recommendations:
        w(f"  {r.agent:<12} backs {r.backs:<10} (conf {r.confidence:.2f}) {r.claim}")
    w("--- OBJECTIONS")
    for o in state.objections:
        cc = f"/{o.cites_constraint}" if o.cites_constraint else ""
        w(f"  {o.from_agent} -> {o.against} [{o.severity}{cc}] {o.outcome}: {o.claim}")
    if state.degraded:
        w(f"--- DEGRADED: {sorted(set(state.degraded))}")
    d = state.decision
    if d:
        w("--- CEO DECISION")
        w(f"  chosen: {d.chosen or '(no feasible portfolio)'}  confidence {d.confidence:.2f}"
          f"{'  [OVERRODE SCORE]' if d.overrode_score else ''}")
        w(f"  {d.statement}")
        for f in p["required_decision_fields"]:
            w(f"    {f}: {d.sections.get(f, '-')}")
        for r in d.rejected:
            w(f"    rejected {r.get('strategy')}: {r.get('reason')}")
        for k in d.kpis:
            w(f"    KPI {k.name}: {k.formula}  base {k.baseline} -> target {k.target} {k.unit}")
        errs = validate(d, p)
        w(f"  validation: {'OK' if not errs else errs}")
    w(f"--- trace: {len(state.trace)} events")
    return "\n".join(out)


def _cmd_intake(args) -> int:
    from boardroom.intake import intake, validate_pack

    pack = intake(args.brief, llm=_llm(args), out=args.out)
    print(f"intake OK → {args.out}  (validate: {validate_pack(pack) or 'clean'})")
    return 0


def _cmd_run(args) -> int:
    pack = json.loads(Path(args.case).read_text(encoding="utf-8"))
    state = run(pack, llm=_llm(args), fail=args.fail)
    path = save_run(state, args.label)
    print(render_text(state))
    print(f"\nwritten: {path}")
    return 0


def _cmd_surprise(args) -> int:
    base = BoardroomState.model_validate_json(Path(args.run).read_text(encoding="utf-8"))
    new = adapt(base, facts=json.loads(Path(args.facts).read_text("utf-8")) if args.facts else None,
                brief=args.brief, llm=_llm(args))
    path = save_run(new, args.label)
    print(render_text(new))
    print(f"\nwritten: {path}")
    return 0


def _cmd_replay(args) -> int:
    state = BoardroomState.model_validate_json(Path(args.run).read_text(encoding="utf-8"))
    print(render_text(state))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="boardroom")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("intake"); pi.add_argument("--brief", required=True)
    pi.add_argument("--out", required=True); pi.add_argument("--stub", action="store_true")
    pi.set_defaults(fn=_cmd_intake)

    pr = sub.add_parser("run"); pr.add_argument("--case", required=True)
    pr.add_argument("--stub", action="store_true"); pr.add_argument("--fail", default=None)
    pr.add_argument("--label", default="baseline"); pr.set_defaults(fn=_cmd_run)

    ps = sub.add_parser("surprise"); ps.add_argument("--run", required=True)
    g = ps.add_mutually_exclusive_group(required=True)
    g.add_argument("--facts"); g.add_argument("--brief")
    ps.add_argument("--stub", action="store_true"); ps.add_argument("--label", default="surprise")
    ps.set_defaults(fn=_cmd_surprise)

    pp = sub.add_parser("replay"); pp.add_argument("run"); pp.set_defaults(fn=_cmd_replay)

    args = ap.parse_args(argv)
    return args.fn(args)


def demo() -> None:
    """Acceptance check - HANDOVER Step 11."""
    RUNS.mkdir(exist_ok=True)
    case = str(Path(__file__).resolve().parent.parent / "cases" / "themeA_tc1.json")

    assert main(["run", "--case", case, "--stub", "--label", "clitest"]) == 0
    latest = max(RUNS.glob("*_clitest.json"), key=lambda p: p.stat().st_mtime)

    # replay builds no LLM and touches no network
    import boardroom.cli as climod
    assert main(["replay", str(latest)]) == 0
    text = render_text(BoardroomState.model_validate_json(latest.read_text("utf-8")))
    assert "CEO DECISION" in text and "CANDIDATES" in text

    # --fail path: agent degraded, decision still made, confidence penalised
    pack = json.loads(Path(case).read_text("utf-8"))
    normal = run(pack, llm=LLM(mode="stub"))
    failed = run(pack, llm=LLM(mode="stub"), fail="credit_risk")
    assert "credit_risk" in failed.degraded
    assert failed.decision is not None
    assert failed.decision.confidence < normal.decision.confidence
    _ = climod  # noqa: silence "imported but unused" in strict linters

    print(f"  run/replay/--fail all green; degraded={failed.degraded}, "
          f"conf {normal.decision.confidence:.2f} -> {failed.decision.confidence:.2f}")
    print("cli.py: all acceptance checks passed")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        demo()
    else:
        raise SystemExit(main())
