"""LLM access — one ``call()`` with a fallback ladder that never raises.

Ladder per call (docs/ARCHITECTURE.md §10):
  1. primary model
  2. retry once            (429 / timeout / transient)
  3. secondary model
  4. last-good cached output for this agent
  5. neutral stub {"status": "unavailable"} + record agent in state.degraded

Stub mode (no API key, or BOARDROOM_LLM=stub) synthesises a schema-valid response with
light heuristics so the whole engine runs offline. The real provider is chosen by
BOARDROOM_LLM (gemini | anthropic | openai) and lazy-imported — no SDK is a hard dep.
"""

from __future__ import annotations

import json
import os
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------- stub

def _first_strategy_id(prompt: str) -> str:
    m = re.search(r"\b(G\d+|S_[a-z]+)\b", prompt)
    return m.group(1) if m else "G1"


def synth(model_cls: type[M], prompt: str) -> dict:
    """Deterministic, schema-valid stub filling only the required fields (defaults cover
    the rest). Just smart enough that the engine produces a non-trivial trace; the sharp
    disagreement comes from the deterministic constraint engine, not from this."""
    out: dict = {}
    sid = _first_strategy_id(prompt)
    for name, f in model_cls.model_fields.items():
        if not f.is_required():
            continue
        ann = str(f.annotation)
        if name in ("backs", "against"):
            out[name] = sid
        elif name in ("agent", "from_agent"):
            out[name] = "stub"
        elif name == "severity":
            out[name] = "minor"
        elif name in ("claim", "rationale", "evidence", "statement"):
            out[name] = f"(stub) {name} for {sid}"
        elif "list" in ann:
            out[name] = []
        elif "dict" in ann:
            out[name] = {}
        elif "bool" in ann:
            out[name] = False
        elif "float" in ann or "int" in ann:
            out[name] = 0.0
        else:
            out[name] = ""
    return out


class _StubProvider:
    name = "stub"

    def __init__(self, faults: list[str] | None = None):
        self.faults = list(faults or [])
        self.calls = 0

    def generate(self, system: str, user: str, model_cls: type[M]) -> str:
        self.calls += 1
        if self.faults:
            fault = self.faults.pop(0)
            if fault == "429":
                raise LLMError("429 rate limited")
            if fault == "outage":
                raise LLMError("connection failed")
            if fault == "badjson":
                return "{ not: valid json,,,"
        return json.dumps(synth(model_cls, f"{system}\n{user}"))


# --------------------------------------------------------------------------- real

def _load_dotenv() -> None:
    """Pull KEY=value pairs from a .env beside the project, or BOARDROOM_ENV, into os.environ.
    Existing environment always wins. Keeps secrets out of the repo."""
    from pathlib import Path

    seen = os.environ.get("BOARDROOM_ENV")
    for p in ([Path(seen)] if seen else []) + [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / "ocr" / ".env",
    ]:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _detect_kind() -> str:
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "gemini"


def _real_provider(kind: str):  # pragma: no cover - needs an SDK + key
    if kind == "openai":
        import openai  # type: ignore

        c = openai.OpenAI()

        class P:
            name = "openai"

            def __init__(self, model: str):
                self.model = model

            def generate_text(self, system, user):
                r = c.chat.completions.create(
                    model=self.model, temperature=0.2,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                )
                return r.choices[0].message.content

            def generate(self, system, user, model_cls):
                return self.generate_text(
                    system + "\n\nReturn ONLY JSON matching:\n"
                    + json.dumps(model_cls.model_json_schema()), user)

        return P("gpt-4o-mini"), P("gpt-4o-mini")

    if kind == "gemini":
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY")
                        or os.environ["GEMINI_API_KEY"])

        class P:
            name = "gemini"

            def __init__(self, model: str):
                self.m = genai.GenerativeModel(model)

            def generate(self, system, user, model_cls):
                return self.generate_text(
                    system + "\n\nReturn ONLY JSON matching this schema:\n"
                    + json.dumps(model_cls.model_json_schema()), user)

            def generate_text(self, system, user):
                return self.m.generate_content(f"{system}\n\n{user}").text

        return (P(os.environ.get("BOARDROOM_MODEL", "gemini-3-flash-preview")),
                P(os.environ.get("BOARDROOM_MODEL2", "gemini-3.1-flash-lite")))

    if kind == "anthropic":
        import anthropic  # type: ignore

        c = anthropic.Anthropic()

        class P:
            name = "anthropic"

            def __init__(self, model: str):
                self.model = model

            def generate(self, system, user, model_cls):
                return self.generate_text(
                    system, f"{user}\n\nReturn ONLY JSON matching:\n"
                    + json.dumps(model_cls.model_json_schema()))

            def generate_text(self, system, user):
                r = c.messages.create(
                    model=self.model, max_tokens=4096, system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return r.content[0].text

        return P("claude-sonnet-5"), P("claude-haiku-4-5-20251001")

    raise LLMError(f"unknown provider {kind!r}")


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text).strip()
    a, b = text.find("{"), text.rfind("}")
    return text[a : b + 1] if a != -1 and b > a else text


# --------------------------------------------------------------------------- api

class LLM:
    def __init__(self, mode: str | None = None, faults: list[str] | None = None):
        _load_dotenv()
        self.mode = mode or os.environ.get("BOARDROOM_LLM", "auto")
        self.cache: dict[str, dict] = {}
        want_real = self.mode not in ("stub",) and (
            self.mode != "auto" or _has_real_creds("auto"))
        if want_real:
            kind = self.mode if self.mode not in ("auto", "real") else \
                os.environ.get("BOARDROOM_PROVIDER") or _detect_kind()
            try:
                self.primary, self.secondary = _real_provider(kind)
                self.mode = kind
                return
            except Exception as e:  # SDK missing / bad config — degrade, don't crash
                print(f"[llm] real provider {kind!r} unavailable ({e}); using stub", flush=True)
        self.primary = self.secondary = _StubProvider(faults)
        self.mode = "stub"

    def call(self, system: str, user: str, model_cls: type[M], *, agent: str,
             state=None) -> M:
        """Return a validated model instance. Never raises — degrades down the ladder."""
        for provider, retries in ((self.primary, 2), (self.secondary, 1)):
            for _ in range(retries):
                try:
                    raw = provider.generate(system, user, model_cls)
                    data = self._parse(raw, model_cls, provider, system, user)
                    obj = model_cls.model_validate(data)
                    self.cache[agent] = data
                    return obj
                except Exception:  # noqa: BLE001 - the ladder must never raise; try next rung
                    continue
        if agent in self.cache:
            return model_cls.model_validate(self.cache[agent])
        if state is not None and agent not in state.degraded:
            state.degraded.append(agent)
        return self._unavailable(model_cls)

    def call_json(self, system: str, user: str) -> dict:
        """Free-form JSON generation (used by intake). Real providers only."""
        if self.mode == "stub":
            raise LLMError("intake needs a real LLM provider — set GOOGLE_API_KEY, "
                           "ANTHROPIC_API_KEY or OPENAI_API_KEY")
        last = None
        for provider in (self.primary, self.secondary):
            for _ in range(2):
                try:
                    return json.loads(_strip_fence(provider.generate_text(system, user)))
                except Exception as e:  # noqa: BLE001
                    last = e
        raise LLMError(f"intake generation failed: {last}")

    def _parse(self, raw: str, model_cls, provider, system, user) -> dict:
        try:
            return json.loads(_strip_fence(raw))
        except json.JSONDecodeError as e:
            fixed = provider.generate(
                system, f"{user}\n\nYour previous reply was not valid JSON ({e}). "
                        f"Return ONLY the JSON object.", model_cls,
            )
            return json.loads(_strip_fence(fixed))

    @staticmethod
    def _unavailable(model_cls: type[M]) -> M:
        data = synth(model_cls, "")
        if "status" in model_cls.model_fields:
            data["status"] = "unavailable"
        if "confidence" in model_cls.model_fields:
            data["confidence"] = 0.0
        return model_cls.model_validate(data)


def _has_real_creds(mode: str) -> bool:
    if mode == "stub":
        return False
    return any(os.environ.get(k) for k in
               ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"))


def demo() -> None:
    """Acceptance check - HANDOVER Step 6: the ladder never raises."""
    from boardroom.state import BoardroomState

    class Reply(BaseModel):
        agent: str
        claim: str
        confidence: float
        status: str = "ok"

    st = BoardroomState(case_id="t", pack={})

    ok = LLM(mode="stub").call("sys", "user G1", Reply, agent="research", state=st)
    assert ok.claim and isinstance(ok.confidence, float)
    assert st.degraded == []

    # 429 on first attempt, then the stub succeeds on retry
    r429 = LLM(mode="stub", faults=["429"]).call("s", "u", Reply, agent="finance", state=st)
    assert r429.status == "ok" and st.degraded == []

    # malformed JSON, then a repair retry that parses
    rbad = LLM(mode="stub", faults=["badjson"]).call("s", "u", Reply, agent="risk", state=st)
    assert rbad.claim.startswith("(stub)")

    # total outage: primary and secondary both fail every attempt -> unavailable + degraded
    dead = LLM(mode="stub", faults=["outage", "outage", "outage"])
    out = dead.call("s", "u", Reply, agent="credit_risk", state=st)
    assert out.status == "unavailable" and out.confidence == 0.0
    assert "credit_risk" in st.degraded

    # cache rung: a good call, then an outage for the same agent -> last-good returned
    live = LLM(mode="stub")
    live.call("s", "u good", Reply, agent="marketing", state=st)
    live.primary = live.secondary = _StubProvider(faults=["outage", "outage", "outage", "outage"])
    cached = live.call("s", "u", Reply, agent="marketing", state=st)
    assert cached.status == "ok" and "marketing" not in st.degraded

    print("llm.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
