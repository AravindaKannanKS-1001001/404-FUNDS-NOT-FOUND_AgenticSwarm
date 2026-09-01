"""Shared state — the only contract between the engine, the agents and the viewer.

The trace is append-only. Everything a judge wants to see is a field here.
`runs/<ts>.json` (a dumped BoardroomState) is the audit record; the UI is a lens over it.

Models are copied from docs/ARCHITECTURE.md §6. Keep them in sync.
"""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["case_pack", "assumption", "surprise", "computed"]
Severity = Literal["minor", "material", "blocking"]


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


class Variable(BaseModel):
    key: str
    value: float | str
    unit: str = ""
    source: Source
    visible_to: list[str]
    note: str = ""


class Violation(BaseModel):
    constraint_id: str
    label: str
    owner: str
    margin: float  # how far over the limit (constraint-native units)


class Strategy(BaseModel):
    id: str
    name: str
    levers: dict[str, float]
    metrics: dict[str, float] = Field(default_factory=dict)  # sandbox only — never an LLM
    violations: list[Violation] = Field(default_factory=list)  # non-empty => infeasible
    score: float = 0.0
    verdict: Literal["selected", "rejected", "viable"] = "viable"
    reject_reason: str = ""
    origin: Literal["search", "seed", "agent"] = "search"


class Recommendation(BaseModel):
    agent: str
    backs: str  # strategy id
    claim: str
    rationale: str
    lever_view: dict[str, float] = Field(default_factory=dict)
    signals: dict[str, float] = Field(default_factory=dict)  # 0-1 scalars this agent owns
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class Objection(BaseModel):
    from_agent: str
    against: str  # agent id or strategy id
    severity: Severity
    claim: str
    evidence: str
    cites_constraint: str = ""  # constraint id, when grounded in one
    response: str = ""  # filled by the rebuttal turn
    outcome: Literal["revised", "defended", "unresolved"] = "unresolved"


class KPI(BaseModel):
    name: str
    formula: str
    baseline: float
    target: float
    unit: str


class Step(BaseModel):
    window: str
    action: str
    owner: str  # responsible business function


class Decision(BaseModel):
    statement: str
    chosen: str = ""  # id of the selected strategy
    sections: dict[str, str] = Field(default_factory=dict)  # keyed by required_decision_fields
    evidence: list[str] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)  # [{"strategy": id, "reason": str}]
    tradeoffs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    implementation: list[Step] = Field(default_factory=list)
    kpis: list[KPI] = Field(default_factory=list)
    overrode_score: bool = False
    override_reason: str = ""
    confidence: float = 0.5


class TraceEvent(BaseModel):
    ts: float
    stage: str
    agent: str
    kind: str
    payload: dict


class BoardroomState(BaseModel):
    run_id: str = Field(default_factory=new_run_id)
    case_id: str
    pack: dict
    variables: list[Variable] = Field(default_factory=list)
    strategies: list[Strategy] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    objections: list[Objection] = Field(default_factory=list)
    decision: Decision | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    round: int = 0
    degraded: list[str] = Field(default_factory=list)  # agent ids running on fallback
    parent_run: str | None = None  # set on a surprise run
    reran: list[str] = Field(default_factory=list)  # surprise: who re-ran
    unchanged: list[dict] = Field(default_factory=list)  # [{"agent":..., "reason":...}]
    invalidated_assumptions: list[str] = Field(default_factory=list)  # TC5 asks by name


def trace(state: BoardroomState, agent: str, kind: str, **payload) -> TraceEvent:
    """Append one event to the append-only trace.

    `stage` may be passed in payload; it is lifted out so the engine can tag events
    with the protocol stage without every caller needing to.
    """
    ev = TraceEvent(
        ts=time.time(),
        stage=payload.pop("stage", ""),
        agent=agent,
        kind=kind,
        payload=payload,
    )
    state.trace.append(ev)
    return ev


def demo() -> None:
    """Acceptance check (HANDOVER Step 1): BoardroomState round-trips through JSON."""
    s = BoardroomState(
        case_id="themeA_tc1",
        pack={"case_id": "themeA_tc1", "roster": []},
        variables=[
            Variable(key="capital", value=3e8, unit="INR", source="case_pack",
                     visible_to=["finance"]),
        ],
    )
    trace(s, "system", "started", stage="0", note="demo")
    s.strategies.append(Strategy(id="A", name="test", levers={"n_mfg": 426.0}))
    s.objections.append(Objection(from_agent="credit_risk", against="A", severity="blocking",
                                  claim="breaches concentration", evidence="73% > 70%",
                                  cites_constraint="concentration"))
    s.decision = Decision(statement="do the thing", confidence=0.7)

    raw = s.model_dump_json()
    back = BoardroomState.model_validate_json(raw)

    assert back.run_id == s.run_id
    assert back.model_dump_json() == raw, "round-trip is not stable"
    assert back.trace[0].stage == "0"
    assert back.trace[0].payload == {"note": "demo"}
    assert back.objections[0].from_agent == "credit_risk"
    assert back.decision.statement == "do the thing"
    assert len(back.run_id) == 8

    # second state gets a distinct run_id (default_factory, not shared mutable)
    s2 = BoardroomState(case_id="x", pack={})
    assert s2.run_id != s.run_id
    assert s2.trace == [] and s.trace != []  # no shared mutable default

    print("state.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
