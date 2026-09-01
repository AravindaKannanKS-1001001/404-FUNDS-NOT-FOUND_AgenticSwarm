"""The 5-stage boardroom protocol.

    stage 0  GENERATE   deterministic candidate search
    stage 1  ANALYSE    every roster agent, in parallel, on its own fact slice
    stage 2  SHARE      recommendations digested into the trace
    stage 3  CHALLENGE   objections + one rebuttal turn; a violated constraint auto-objects
    stage 4  COMPARE     weighted ranking; infeasible strategies sink
    stage 5  DECIDE      CEO -> Decision, validated in code, one repair retry, then backfill

The trace is written so it maps 1:1 onto rulebook §3. Nothing here is domain-specific.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from boardroom import agents
from boardroom.generate import candidates
from boardroom.llm import LLM
from boardroom.scoring import rank
from boardroom.state import (
    BoardroomState, Decision, KPI, Objection, Step, Variable, new_run_id, trace,
)

MAX_ROUNDS = 3
RUNS = Path(__file__).resolve().parent.parent / "runs"


# --------------------------------------------------------------------- fail inject

class _FailInjector:
    """Force one agent onto the fallback path — the rulebook's demanded failure demo."""

    def __init__(self, inner: LLM, agent: str):
        self.inner, self.agent = inner, agent
        self.mode = f"{inner.mode}+fail:{agent}"
        self.cache = inner.cache

    def call(self, system, user, model_cls, *, agent, state=None):
        if agent.split(":")[0] == self.agent:
            if state is not None and self.agent not in state.degraded:
                state.degraded.append(self.agent)
            return LLM._unavailable(model_cls)
        return self.inner.call(system, user, model_cls, agent=agent, state=state)


# --------------------------------------------------------------------- stages

def _roster_ids(pack: dict) -> list[str]:
    return [r["id"] for r in pack["roster"]]


def _generate(state: BoardroomState) -> None:
    state.strategies = candidates(state.pack)
    obj = state.pack["objective"]
    for s in state.strategies:
        trace(state, "search", "candidate", stage="0", id=s.id, origin=s.origin,
              objective=s.metrics.get(obj), feasible=not s.violations,
              violations=[v.constraint_id for v in s.violations])


def _parallel(ids: list[str], fn):
    with ThreadPoolExecutor(max_workers=max(1, len(ids))) as ex:
        return list(ex.map(fn, ids))  # ex.map preserves input order


def _analyse(state: BoardroomState, llm) -> None:
    def one(aid: str):
        return aid, agents.analyse_call(llm, state.pack, aid, state.strategies,
                                        state.variables, state)

    for aid, rec in _parallel(_roster_ids(state.pack), one):
        state.recommendations.append(rec)
        trace(state, aid, "recommendation", stage="1", backs=rec.backs, claim=rec.claim,
              signals=rec.signals, confidence=rec.confidence)


def _digest(state: BoardroomState) -> str:
    lines = []
    for r in state.recommendations:
        lines.append(f"{r.agent} backs [{r.backs}] (conf {r.confidence:.2f}): {r.claim}")
    for o in state.objections:
        lines.append(f"{o.from_agent} objects to {o.against} [{o.severity}]: {o.claim}")
    return "\n".join(lines)


def _share(state: BoardroomState) -> None:
    trace(state, "system", "share", stage="2", digest=_digest(state),
          recommendations=len(state.recommendations))


def _auto_block(state: BoardroomState) -> None:
    """Every constraint violation becomes a blocking objection from the owning agent."""
    for s in state.strategies:
        for v in s.violations:
            state.objections.append(Objection(
                from_agent=v.owner, against=s.id, severity="blocking",
                claim=f"{s.id} violates {v.constraint_id}: {v.label}",
                evidence=f"over the limit by {v.margin:,.2f}",
                cites_constraint=v.constraint_id, outcome="defended"))
            trace(state, v.owner, "auto_objection", stage="3", against=s.id,
                  cites=v.constraint_id)


def _rebuttal(state: BoardroomState, llm, objs: list[Objection]) -> None:
    roster = set(_roster_ids(state.pack))
    for o in objs:
        if o.severity not in ("material", "blocking"):
            continue
        if o.against not in roster:
            o.outcome = "defended"  # aimed at a strategy/constraint — it stands
            continue
        prior = next((r for r in state.recommendations if r.agent == o.against), None)
        if prior is None:
            o.outcome = "unresolved"
            continue
        revised = agents.analyse_call(llm, state.pack, o.against, state.strategies,
                                      state.variables, state)
        if revised.backs != prior.backs or revised.lever_view != prior.lever_view:
            prior.backs, prior.lever_view, prior.rationale = (
                revised.backs, revised.lever_view, revised.rationale)
            o.outcome = "revised"
        else:
            o.outcome = "defended"
        o.response = revised.claim
        trace(state, o.against, "rebuttal", stage="3", to=o.from_agent, outcome=o.outcome)


def _unresolved_material(state: BoardroomState) -> bool:
    return any(o.severity == "material" and o.outcome == "unresolved"
               for o in state.objections)


def _challenge(state: BoardroomState, llm) -> None:
    _auto_block(state)
    while state.round < MAX_ROUNDS:
        state.round += 1
        digest = _digest(state)

        def one(aid: str):
            return aid, agents.challenge_call(llm, state.pack, aid, state.strategies,
                                              state.variables, digest, state)

        fresh: list[Objection] = []
        for aid, objs in _parallel(_roster_ids(state.pack), one):
            for o in objs:
                fresh.append(o)
                trace(state, aid, "objection", stage="3", against=o.against,
                      severity=o.severity, cites=o.cites_constraint)
        state.objections.extend(fresh)
        _rebuttal(state, llm, fresh)
        if not _unresolved_material(state):
            break
    trace(state, "system", "challenge_done", stage="3", rounds=state.round,
          objections=len(state.objections))


def _compare(state: BoardroomState) -> None:
    signals: dict = {}
    for r in state.recommendations:
        signals.update(r.signals)
    ranked = rank(state.strategies, signals, state.pack)
    state.strategies = ranked
    for s in ranked:
        if s.violations:
            s.verdict = "rejected"
            s.reject_reason = "infeasible: " + ", ".join(v.constraint_id for v in s.violations)
        else:
            s.verdict = "viable"
    trace(state, "system", "ranking", stage="4",
          order=[{"id": s.id, "score": round(s.score, 4), "feasible": not s.violations}
                 for s in ranked])


def validate(dec: Decision, pack: dict) -> list[str]:
    errs = []
    for f in pack["required_decision_fields"]:
        if not dec.sections.get(f, "").strip():
            errs.append(f"missing required decision section: {f}")
    if len(dec.rejected) < 1:
        errs.append("need >=1 rejected alternative with a reason")
    if len(dec.kpis) < 3:
        errs.append("need >=3 KPIs with formula/baseline/target")
    if not dec.implementation:
        errs.append("need an implementation sequence with owning functions")
    if not dec.evidence:
        errs.append("must cite department evidence")
    if not dec.tradeoffs:
        errs.append("must state trade-offs")
    if dec.overrode_score and not dec.override_reason.strip():
        errs.append("override of the ranking must be justified")
    return errs


def _default_kpis(pack: dict, chosen) -> list[KPI]:
    out = []
    for key, direction in list(pack.get("direction", {}).items())[:3]:
        target = chosen.metrics.get(key, 0.0) if chosen else 0.0
        out.append(KPI(name=key.replace("_", " ").title(),
                       formula=pack["metrics"].get(key, key),
                       baseline=0.0, target=round(target, 2),
                       unit="INR" if "income" in key or "deployed" in key else "ratio"))
    while len(out) < 3:
        out.append(KPI(name=f"Guardrail {len(out) + 1}", formula="n/a",
                       baseline=0.0, target=0.0, unit="ratio"))
    return out


def _backfill(dec: Decision, pack: dict, ranked: list, errs: list[str]) -> Decision:
    chosen = next((s for s in ranked if not s.violations), ranked[0] if ranked else None)
    cid = chosen.id if chosen else ""
    for f in pack["required_decision_fields"]:
        dec.sections.setdefault(f, f"[auto] {f.replace('_', ' ')} as implied by strategy {cid}.")
    if not dec.rejected:
        rej = next((s for s in ranked if s.violations), None)
        if rej:
            dec.rejected = [{"strategy": rej.id, "reason": rej.reject_reason}]
    if len(dec.kpis) < 3:
        dec.kpis = _default_kpis(pack, chosen)
    if not dec.implementation:
        dec.implementation = [
            Step(window="0-2 weeks", action=f"Stand up strategy {cid}", owner="operations"),
            Step(window="2-8 weeks", action="Originate to the approved mix", owner="sales"),
        ]
    if not dec.evidence:
        dec.evidence = ["search: feasible optimum", "credit_risk: constraint review"]
    if not dec.tradeoffs:
        dec.tradeoffs = ["expected return traded against segment concentration"]
    if not dec.statement:
        dec.statement = f"Adopt strategy {cid}."
    dec.chosen = dec.chosen or cid
    return dec


def _decide(state: BoardroomState, llm) -> None:
    ranked = state.strategies
    extra = ""
    errs: list[str] = []
    for _ in range(2):
        dec = agents.decide_call(llm, state.pack, ranked, state.recommendations,
                                 state.objections, state.degraded, state, extra)
        errs = validate(dec, state.pack)
        if not errs:
            break
        extra = "\n\nYour previous reply was rejected for:\n" + "\n".join(f"- {e}" for e in errs)
        trace(state, "ceo", "decision_rejected", stage="5", errors=errs)
    if errs:
        dec = _backfill(dec, state.pack, ranked, errs)
        dec.confidence *= 0.8
        trace(state, "ceo", "decision_backfilled", stage="5", filled=errs)

    feasible = [s for s in ranked if not s.violations]
    chosen = next((s for s in ranked if s.id == dec.chosen), None)
    if not feasible:
        # the surprise (or the case) leaves nothing feasible — a real outcome. The CEO's
        # decision stands as "no viable portfolio; redesign/pause"; do not fake a pick.
        dec.chosen = ""
        trace(state, "system", "no_feasible_candidate", stage="5",
              note="every candidate violates a hard constraint")
    elif chosen is None or chosen.violations:
        trace(state, "system", "chosen_corrected", stage="5",
              was=dec.chosen or "(none)", to=feasible[0].id,
              reason="CEO pick was infeasible or unknown" if dec.chosen else "CEO named no strategy")
        dec.chosen = feasible[0].id
    dec.confidence *= 0.8 ** len(set(state.degraded))
    state.decision = dec

    for s in ranked:
        if s.id == dec.chosen and not s.violations:
            s.verdict = "selected"
    for r in dec.rejected:
        for s in ranked:
            if s.id == r.get("strategy"):
                s.verdict = "rejected"
    trace(state, "ceo", "decided", stage="5", chosen=dec.chosen,
          confidence=round(dec.confidence, 3), overrode=dec.overrode_score,
          degraded=state.degraded)


# --------------------------------------------------------------------- entry

def run(pack: dict, llm=None, fail: str | None = None) -> BoardroomState:
    llm = llm or LLM()
    if fail:
        llm = _FailInjector(llm, fail)
    state = BoardroomState(
        case_id=pack["case_id"], pack=pack,
        variables=[Variable(**v) for v in pack["variables"]],
    )
    trace(state, "system", "run_started", stage="0",
          mode=getattr(llm, "mode", "?"), roster=_roster_ids(pack))
    _generate(state)
    _analyse(state, llm)
    _share(state)
    _challenge(state, llm)
    _compare(state)
    _decide(state, llm)
    trace(state, "system", "run_done", stage="5")
    return state


# --------------------------------------------------------------------- surprise

def _sync_pack_vars(state: BoardroomState) -> None:
    """generate()/compute() read pack['variables'], not state.variables — keep them equal."""
    state.pack["variables"] = [v.model_dump() for v in state.variables]


def _apply_delta(state: BoardroomState, facts: dict) -> list[str]:
    by_key = {v.key: v for v in state.variables}
    changed = []
    for k, val in facts.items():
        if k.startswith("_"):
            continue
        if k in by_key:
            by_key[k].value = val
            by_key[k].source = "surprise"
        else:
            state.variables.append(Variable(key=k, value=val, unit="", source="surprise",
                                            visible_to=[], note="introduced by the surprise"))
        changed.append(k)
    _relabel_constraints(state, facts, changed)
    _sync_pack_vars(state)
    return changed


def _relabel_constraints(state: BoardroomState, facts: dict, changed: list[str]) -> None:
    """A constraint's label is the brief's original sentence. When the surprise moves a
    limit the expression references, that sentence goes stale — say so, rather than
    printing '5%' while enforcing 5.5%."""
    for c in state.pack["constraints"]:
        moved = [k for k in changed if k in c["expr"] and isinstance(facts.get(k), (int, float))]
        if moved and "revised to" not in c["label"]:
            c["label"] += " [revised to " + ", ".join(
                f"{k}={facts[k]:g}" for k in moved) + " by the surprise]"


def _pack_diff(old: dict, new: dict) -> list[str]:
    o = {v["key"]: v["value"] for v in old.get("variables", [])}
    n = {v["key"]: v["value"] for v in new.get("variables", [])}
    return [k for k in n if o.get(k) != n[k]] + [k for k in o if k not in n]


def _rerun_affected(state: BoardroomState, llm, baseline: BoardroomState) -> None:
    prior = {r.agent: r for r in baseline.recommendations}

    def one(aid: str):
        if aid in state.reran or aid not in prior:
            return aid, ("fresh", agents.analyse_call(llm, state.pack, aid, state.strategies,
                                                      state.variables, state))
        return aid, ("carried", prior[aid])

    for aid, (how, rec) in _parallel(_roster_ids(state.pack), one):
        state.recommendations.append(rec)
        trace(state, aid, "recommendation" if how == "fresh" else "carried_forward",
              stage="1", backs=rec.backs, claim=rec.claim, signals=rec.signals)


def adapt(baseline: BoardroomState, *, facts: dict | None = None,
          brief: str | Path | None = None, llm=None) -> BoardroomState:
    """Surprise adaptation. `facts` = a variable delta (TC2/TC5); `brief` = a whole new
    pack via intake (TC3/TC4). Re-runs only the agents whose visible facts moved."""
    from boardroom.intake import intake

    if not facts and not brief:
        raise ValueError("adapt needs facts= or brief=")
    llm = llm or LLM()

    new = baseline.model_copy(deep=True)
    new.parent_run, new.run_id = baseline.run_id, new_run_id()
    new.trace, new.recommendations, new.objections = [], [], []
    new.decision, new.round, new.degraded = None, 0, []
    new.reran, new.unchanged, new.invalidated_assumptions = [], [], []

    base_vals = {v.key: v.value for v in baseline.variables}

    if facts:
        mode = "delta"
        changed = _apply_delta(new, facts)
    else:
        mode = "reintake"
        new.pack = intake(brief, llm=llm)
        new.variables = [Variable(**v) for v in new.pack["variables"]]
        changed = _pack_diff(baseline.pack, new.pack)

    ids = _roster_ids(new.pack)
    vis = {v.key: set(v.visible_to) for v in new.variables}
    affected: set[str] = set()
    for k in changed:
        affected |= vis.get(k, set())

    unknown = [k for k in changed if k not in vis or not vis[k]]
    if unknown and facts:  # a fact with no owner -> can't scope it, wake everyone
        affected = set(ids)
        trace(new, "system", "impact_fallback", stage="s", keys=unknown)

    new.reran = sorted(a for a in affected if a in ids)
    new.unchanged = [{"agent": a, "reason": f"no visibility on {sorted(changed)}"}
                     for a in ids if a not in new.reran]
    new.invalidated_assumptions = [
        f"{k}: {base_vals.get(k, '(new)')} -> {next(v.value for v in new.variables if v.key == k)}"
        for k in changed
    ]

    trace(new, "system", "surprise", stage="s", mode=mode, changed=sorted(changed),
          reran=new.reran, unchanged=[u["agent"] for u in new.unchanged])
    for u in new.unchanged:
        trace(new, u["agent"], "skipped", stage="s", reason=u["reason"])

    _generate(new)
    _rerun_affected(new, llm, baseline)
    _share(new)
    _challenge(new, llm)
    _compare(new)
    _decide(new, llm)
    trace(new, "system", "run_done", stage="5")
    return new


def save_run(state: BoardroomState, label: str = "baseline") -> Path:
    RUNS.mkdir(exist_ok=True)
    path = RUNS / f"{int(time.time())}_{state.run_id}_{label}.json"
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return path


def demo() -> None:
    """Acceptance check - HANDOVER Step 8: stub run completes every stage, writes JSON."""
    from boardroom.oracles import load_pack

    pack = load_pack("themeA_tc1")
    state = run(pack, llm=LLM(mode="stub"))

    stages = {e.stage for e in state.trace}
    assert stages >= {"0", "1", "2", "3", "4", "5"}, f"missing stages: {stages}"
    assert len(state.recommendations) == len(pack["roster"])
    assert state.decision is not None
    assert validate(state.decision, pack) == [], validate(state.decision, pack)
    assert state.decision.chosen in {s.id for s in state.strategies}

    sel = [s for s in state.strategies if s.verdict == "selected"]
    assert len(sel) == 1 and not sel[0].violations, "selected an infeasible strategy"

    # the greedy seed was auto-rejected by its constraint owners
    auto = [e for e in state.trace if e.kind == "auto_objection"]
    assert any(e.payload["against"] == "S_greedy" for e in auto)
    owners = {e.agent for e in auto if e.payload["against"] == "S_greedy"}
    assert owners >= {"credit_risk", "finance"}, owners

    path = save_run(state)
    reloaded = BoardroomState.model_validate_json(path.read_text(encoding="utf-8"))
    assert reloaded.run_id == state.run_id

    # --- Step 10: delta-mode surprise, selective re-run ---
    delta = json.loads(Path(RUNS.parent / "briefs" / "themeA_tc2.facts.json").read_text("utf-8"))
    sp = adapt(state, facts=delta, llm=LLM(mode="stub"))
    reran, skipped = set(sp.reran), {u["agent"] for u in sp.unchanged}
    assert reran >= {"credit_risk", "finance"}, reran
    assert {"research", "marketing"} <= skipped, skipped
    assert all(u["reason"] for u in sp.unchanged)
    assert sp.invalidated_assumptions and any("default_limit" in a for a in sp.invalidated_assumptions)
    assert sp.parent_run == state.run_id
    assert sp.decision is not None and validate(sp.decision, sp.pack) == []
    assert any(e.kind == "skipped" for e in sp.trace)
    # TC2's real numbers leave NO feasible portfolio (the 70% concentration cap forces >=30%
    # of the book into a >=7%-default segment, breaching the 5.5% cap). That is the correct
    # answer, so accept it: select exactly one feasible strategy, or select none and say so.
    sp_sel = [s for s in sp.strategies if s.verdict == "selected"]
    sp_feasible = [s for s in sp.strategies if not s.violations]
    if sp_feasible:
        assert len(sp_sel) == 1 and not sp_sel[0].violations, "selected an infeasible strategy"
    else:
        assert not sp_sel and sp.decision.chosen == "", "claimed a pick with nothing feasible"
        assert any(e.kind == "no_feasible_candidate" for e in sp.trace), "infeasibility not traced"

    print(f"  stages seen        : {sorted(stages)}")
    print(f"  recommendations    : {len(state.recommendations)}")
    print(f"  objections         : {len(state.objections)} "
          f"({sum(o.severity == 'blocking' for o in state.objections)} blocking)")
    print(f"  ranking            : {[(s.id, round(s.score, 3)) for s in state.strategies]}")
    print(f"  CEO chose          : {state.decision.chosen} "
          f"(conf {state.decision.confidence:.2f}, overrode={state.decision.overrode_score})")
    print(f"  trace events       : {len(state.trace)}")
    print(f"  written            : {path.name}")
    print(f"  surprise re-ran    : {sp.reran}")
    print(f"  surprise skipped   : {[u['agent'] for u in sp.unchanged]}")
    print(f"  invalidated        : {sp.invalidated_assumptions}")
    print(f"  revised CEO choice : {sp.decision.chosen} (was {state.decision.chosen})")
    print("engine.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
