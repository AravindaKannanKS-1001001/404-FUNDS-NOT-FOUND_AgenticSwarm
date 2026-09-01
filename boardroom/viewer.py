"""Streamlit lens over runs/*.json. Read-only, except a weight re-score that runs no LLM.

    streamlit run boardroom/viewer.py

Expendable — the CLI is the system. If this breaks during the demo, `boardroom replay`
shows the same content.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from boardroom.scoring import rank
from boardroom.state import BoardroomState

RUNS = Path(__file__).resolve().parent.parent / "runs"

st.set_page_config(page_title="AI Boardroom", layout="wide")

files = sorted(RUNS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
if not files:
    st.warning("No runs yet. `python -m boardroom run --case cases/themeA_tc1.json`")
    st.stop()

pick = st.sidebar.selectbox("run", files, format_func=lambda p: p.name)
state = BoardroomState.model_validate_json(pick.read_text(encoding="utf-8"))
pack = state.pack

st.title(f"{pack.get('company', '?')} — {state.case_id}")
st.caption(pack["decision_question"])
if state.parent_run:
    st.info(f"Surprise run on `{state.parent_run}` · re-ran **{', '.join(state.reran)}** · "
            f"skipped **{', '.join(u['agent'] for u in state.unchanged)}**")
    st.write("Invalidated assumptions:", state.invalidated_assumptions)

st.sidebar.subheader("Re-score (no LLM)")
weights = {k: st.sidebar.slider(k, 0.0, 1.0, float(v), 0.05)
           for k, v in pack["weights"].items()}
total = sum(weights.values()) or 1.0
pack_w = {**pack, "weights": {k: v / total for k, v in weights.items()}}
signals: dict = {}
for r in state.recommendations:
    signals.update(r.signals)
ranked = rank(list(state.strategies), signals, pack_w)

st.subheader("Candidates")
st.dataframe([
    {"id": s.id, "verdict": s.verdict, "score": round(s.score, 3),
     **{k: round(v, 3) for k, v in s.levers.items()},
     "violations": ", ".join(v.constraint_id for v in s.violations) or "—"}
    for s in ranked
], use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Recommendations")
    for r in state.recommendations:
        st.markdown(f"**{r.agent}** → `{r.backs}` (conf {r.confidence:.2f})  \n{r.claim}")
with c2:
    st.subheader("Objections")
    for o in state.objections:
        cc = f" · `{o.cites_constraint}`" if o.cites_constraint else ""
        st.markdown(f"**{o.from_agent} → {o.against}** [{o.severity}{cc}] — *{o.outcome}*  \n{o.claim}")

if state.degraded:
    st.error(f"Degraded agents (ran on fallback): {sorted(set(state.degraded))}")

d = state.decision
if d:
    st.subheader("CEO Decision")
    st.markdown(f"**Chosen:** `{d.chosen or 'no feasible portfolio'}` · "
                f"confidence {d.confidence:.2f}"
                + ("  · **OVERRODE SCORE**" if d.overrode_score else ""))
    st.write(d.statement)
    for f in pack["required_decision_fields"]:
        st.markdown(f"- **{f}**: {d.sections.get(f, '—')}")
    st.write("Rejected:", d.rejected)
    st.write("KPIs:", [k.model_dump() for k in d.kpis])

with st.expander("Full trace"):
    st.json([json.loads(e.model_dump_json()) for e in state.trace])
