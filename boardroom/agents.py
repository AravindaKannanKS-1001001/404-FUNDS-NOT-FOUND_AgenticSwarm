"""Agents — the roster comes from the pack; one function drives every department.

No per-agent Python. `facts_for` derives each agent's fact slice from `visible_to`, so
an agent literally cannot reason about a variable it was not shown. The CEO is the only
role with its own template.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from pydantic import BaseModel

from boardroom.state import (
    BoardroomState, Decision, Objection, Recommendation, Strategy, Variable,
)

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


class ObjectionSet(BaseModel):
    objections: list[Objection] = []


def _tpl(name: str) -> Template:
    return Template((PROMPTS / name).read_text(encoding="utf-8"))


def facts_for(agent_id: str, variables: list[Variable]) -> list[Variable]:
    return [v for v in variables if agent_id in v.visible_to]


def spec_for(pack: dict, agent_id: str) -> dict:
    return next(r for r in pack["roster"] if r["id"] == agent_id)


def owned_constraints(pack: dict, agent_id: str) -> list[dict]:
    return [c for c in pack["constraints"] if c["owner"] == agent_id]


# ------------------------------------------------------------------ rendering

def _fmt_vars(variables: list[Variable]) -> str:
    if not variables:
        return "(none — you have no direct visibility; rely on the candidate metrics)"
    out = []
    for v in variables:
        tag = "FACT" if v.source == "case_pack" else v.source.upper()
        note = f"  — {v.note}" if v.note else ""
        out.append(f"- {v.key} = {v.value} {v.unit} [{tag}]{note}")
    return "\n".join(out)


def _fmt_strategies(strategies: list[Strategy], show_keys: list[str] | None = None) -> str:
    rows = []
    for s in strategies:
        levers = " ".join(f"{k}={v:g}" for k, v in s.levers.items())
        keys = show_keys or list(s.metrics)[:4]
        mets = " ".join(f"{k}={s.metrics[k]:,.0f}" for k in keys if k in s.metrics)
        if s.violations:
            v = "INFEASIBLE: " + ", ".join(f"{x.constraint_id}" for x in s.violations)
        else:
            v = "feasible"
        rows.append(f"- [{s.id}] {s.name} | {levers} | {mets} | {v}")
    return "\n".join(rows)


def _fmt_constraints(cons: list[dict]) -> str:
    return "\n".join(f"- {c['id']}: {c['label']}" for c in cons) or "(none)"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items)


def render_department(pack: dict, agent_id: str, strategies: list[Strategy],
                      variables: list[Variable], challenge: str = "") -> tuple[str, str]:
    spec = spec_for(pack, agent_id)
    body = _tpl("_department.md").substitute(
        title=spec["title"],
        company=pack.get("company", "the company"),
        decision_question=pack["decision_question"],
        problem=pack["problem"],
        mandate=spec["mandate"],
        guardrails=_bullets(pack["guardrails"]),
        variables=_fmt_vars(facts_for(agent_id, variables)),
        strategies=_fmt_strategies(strategies),
        constraints=_fmt_constraints(owned_constraints(pack, agent_id)),
        signals=", ".join(spec["signals"]),
        challenge=challenge,
    )
    system = f"You are a company's {spec['title']}. Answer only as that role, in JSON."
    return system, body


def render_ceo(pack: dict, ranked: list[Strategy], recs: list[Recommendation],
               objs: list[Objection], degraded: list[str]) -> tuple[str, str]:
    ceo = pack["ceo"]
    ranked_txt = "\n".join(
        f"- #{i + 1} [{s.id}] {s.name} | score={s.score:.3f} | "
        f"{'INFEASIBLE (' + ','.join(x.constraint_id for x in s.violations) + ')' if s.violations else 'feasible'}"
        for i, s in enumerate(ranked)
    )
    recs_txt = "\n".join(
        f"- {r.agent} backs [{r.backs}] (conf {r.confidence:.2f}): {r.claim}" for r in recs
    ) or "(none)"
    objs_txt = "\n".join(
        f"- {o.from_agent} vs {o.against} [{o.severity}"
        f"{'/' + o.cites_constraint if o.cites_constraint else ''}]: {o.claim}"
        f"{'  -> ' + o.outcome if o.outcome != 'unresolved' else ''}"
        for o in objs
    ) or "(none)"
    degraded_txt = (
        f"\nDEGRADED: {', '.join(degraded)} ran on fallback — lower your confidence and "
        f"note this under risks." if degraded else ""
    )
    body = _tpl("_ceo.md").substitute(
        title=ceo["title"],
        company=pack.get("company", "the company"),
        decision_question=pack["decision_question"],
        problem=pack["problem"],
        objective=ceo["objective"],
        guardrails=_bullets(pack["guardrails"]),
        ranked=ranked_txt,
        recommendations=recs_txt,
        objections=objs_txt,
        degraded=degraded_txt,
        required_fields=", ".join(pack["required_decision_fields"]),
    )
    system = f"You are a company's {ceo['title']}. Return one JSON decision object."
    return system, body


# ------------------------------------------------------------------ execution
# These call the LLM and return a parsed object. They do NOT touch state — the engine
# owns the trace and the ordering (stage 1 runs the roster in parallel).

def analyse_call(llm, pack: dict, agent_id: str, strategies: list[Strategy],
                 variables: list[Variable], state: BoardroomState) -> Recommendation:
    system, user = render_department(pack, agent_id, strategies, variables)
    rec = llm.call(system, user, Recommendation, agent=agent_id, state=state)
    rec.agent = agent_id  # trust our id, never the model's
    return rec


def challenge_call(llm, pack: dict, agent_id: str, strategies: list[Strategy],
                   variables: list[Variable], digest: str,
                   state: BoardroomState) -> list[Objection]:
    block = _tpl("_challenge.md").substitute(digest=digest)
    system, user = render_department(pack, agent_id, strategies, variables, block)
    result = llm.call(system, user, ObjectionSet, agent=f"{agent_id}:challenge", state=state)
    for o in result.objections:
        o.from_agent = agent_id
    return list(result.objections)


def decide_call(llm, pack: dict, ranked: list[Strategy], recs: list[Recommendation],
                objs: list[Objection], degraded: list[str],
                state: BoardroomState, extra: str = "") -> Decision:
    system, user = render_ceo(pack, ranked, recs, objs, degraded)
    return llm.call(system, user + extra, Decision, agent="ceo", state=state)


def demo() -> None:
    """Acceptance check - HANDOVER Step 7."""
    from boardroom.oracles import load_pack
    from boardroom.generate import candidates

    pack = load_pack("themeA_tc1")
    variables = [Variable(**v) for v in pack["variables"]]
    strats = candidates(pack, k=3)

    system, user = render_department(pack, "credit_risk", strats, variables)

    # only credit_risk's variables appear
    cr_keys = {v.key for v in facts_for("credit_risk", variables)}
    other_keys = {v.key for v in variables} - cr_keys
    assert "retail_default" in cr_keys and "retail_default" in user
    assert "retail_acq" in other_keys and "retail_acq" not in user, "leaked a hidden variable"
    assert "cost_of_funds" not in user, "leaked finance-only variable"

    # both guardrails present
    for g in pack["guardrails"]:
        assert g in user, f"missing guardrail: {g[:40]}"

    # only credit_risk's owned constraints
    assert "default_cap" in user and "concentration" in user
    assert "rate_cap" not in user.split("HARD CONSTRAINTS YOU OWN")[1].split("RULES")[0], \
        "showed a constraint credit_risk does not own"

    # the infeasible greedy seed is shown as such
    assert "INFEASIBLE" in user

    print(f"  credit_risk sees {len(cr_keys)} variables, hidden from it: {len(other_keys)}")
    print("  owned constraints in prompt:", [c["id"] for c in owned_constraints(pack, "credit_risk")])
    print("agents.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
