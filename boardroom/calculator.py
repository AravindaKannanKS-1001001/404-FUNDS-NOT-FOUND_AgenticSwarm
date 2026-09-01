"""Sandboxed expression evaluator — the arithmetic core.

An LLM writes the metric and constraint expressions in the case pack, so they are
semi-untrusted. We whitelist the AST and never ``eval`` raw text. No attribute access,
no subscripting, no imports, no comprehensions, no ``__builtins__``. Unknown names are
rejected before compilation.

Contract (docs/ARCHITECTURE.md §3):
    safe_eval(expr, ns)            -> float | bool
    compute(metrics, ns)          -> dict[str, float]      (metrics may chain)
    check(constraints, ns)        -> list[dict]            (the VIOLATED ones)

Anything that goes wrong evaluating an expression surfaces as ``ValueError`` so callers
(generate.py, the validator) can catch one exception type.
"""

from __future__ import annotations

import ast
import math
from functools import lru_cache

ALLOWED = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.IfExp,
    ast.Call, ast.Name, ast.Load, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.And, ast.Or, ast.Not,
)

FUNCS = {
    "min": min, "max": max, "abs": abs, "round": round,
    "exp": math.exp, "sqrt": lambda x: math.sqrt(max(x, 0.0)),
    "log": lambda x: math.log(max(x, 1e-9)),
}


@lru_cache(maxsize=1024)
def _compile(expr: str):
    """Parse, whitelist-check and compile one expression. Cached — the candidate
    generator evaluates the same ~20 expressions tens of thousands of times.
    Returns (code_object, set_of_referenced_names). Raises ValueError if disallowed."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"syntax error in {expr!r}: {e}") from e
    for n in ast.walk(tree):
        if not isinstance(n, ALLOWED):
            raise ValueError(f"disallowed syntax {type(n).__name__} in {expr!r}")
        if isinstance(n, ast.Call) and (
            not isinstance(n.func, ast.Name) or n.func.id not in FUNCS
        ):
            raise ValueError(f"disallowed call in {expr!r}")
    names = frozenset(n.id for n in ast.walk(tree) if isinstance(n, ast.Name))
    return compile(tree, "<metric>", "eval"), names


def safe_eval(expr: str, ns: dict):
    """Evaluate one whitelisted expression. Raises ValueError on anything disallowed,
    an unresolved name, or any arithmetic failure (division by zero, overflow)."""
    code, names = _compile(expr)
    missing = names - FUNCS.keys() - ns.keys()
    if missing:
        raise ValueError(f"unknown name {sorted(missing)[0]!r} in {expr!r}")
    try:
        return eval(  # noqa: S307 - AST is whitelisted in _compile
            code, {"__builtins__": {}}, {**FUNCS, **ns}
        )
    except (ArithmeticError, TypeError) as e:  # zero-div, overflow, or a bad-typed value
        raise ValueError(f"could not evaluate {expr!r}: {e}") from e


def compute(metrics: dict[str, str], ns: dict) -> dict[str, float]:
    """Resolve a dict of named expressions. A metric may reference an earlier metric;
    we run repeated passes until everything resolves or nothing progresses."""
    out, pending = dict(ns), dict(metrics)
    for _ in range(len(metrics) + 1):
        if not pending:
            break
        progressed = False
        for k, expr in list(pending.items()):
            try:
                out[k] = safe_eval(expr, out)
                del pending[k]
                progressed = True
            except ValueError:
                pass  # unresolved name this pass — retry next pass
        if not progressed:
            # re-raise the real reason rather than a generic message
            errs = {}
            for k, expr in pending.items():
                try:
                    safe_eval(expr, out)
                except ValueError as e:
                    errs[k] = str(e)
            raise ValueError(f"unresolvable or circular metrics: {errs}")
    return {k: out[k] for k in metrics}


def check(constraints: list[dict], ns: dict) -> list[dict]:
    """Return the constraints that are VIOLATED under ``ns`` (empty list == feasible).

    Each returned dict is the original constraint plus a ``margin`` — how far the
    left side sits past the limit, in the constraint's own units. A constraint whose
    expression cannot evaluate is reported as violated with margin ``inf`` rather than
    silently passing.
    """
    violated = []
    for c in constraints:
        try:
            ok = safe_eval(c["expr"], ns)
        except ValueError:
            violated.append({**c, "margin": float("inf")})
            continue
        if not ok:
            violated.append({**c, "margin": _margin(c["expr"], ns)})
    return violated


def _margin(expr: str, ns: dict) -> float:
    """For a top-level comparison ``lhs OP rhs``, return |lhs - rhs|. 0.0 otherwise."""
    try:
        tree = ast.parse(expr, mode="eval").body
        if isinstance(tree, ast.Compare) and len(tree.comparators) == 1:
            lhs = safe_eval(ast.unparse(tree.left), ns)
            rhs = safe_eval(ast.unparse(tree.comparators[0]), ns)
            return abs(float(lhs) - float(rhs))
    except (ValueError, AttributeError):
        pass
    return 0.0


def demo() -> None:
    """Acceptance check — HANDOVER Step 2."""

    def raises(fn):
        try:
            fn()
        except ValueError:
            return True
        return False

    # hostile input
    assert raises(lambda: safe_eval("__import__('os')", {})), "import not blocked"
    assert raises(lambda: safe_eval("().__class__", {})), "attribute access not blocked"
    assert raises(lambda: safe_eval("x.attr", {"x": 1})), "attribute access not blocked"
    assert raises(lambda: safe_eval("[i for i in range(3)]", {})), "comprehension not blocked"
    assert raises(lambda: safe_eval("open('x')", {})), "arbitrary call not blocked"
    assert raises(lambda: safe_eval("unknown_var + 1", {})), "unknown name not blocked"

    # circular / unresolvable metrics
    assert raises(lambda: compute({"a": "b + 1", "b": "a + 1"}, {})), "circular not caught"

    # guarded division
    assert compute({"a": "1/max(x,1)"}, {"x": 0}) == {"a": 1.0}
    # unguarded division by zero -> ValueError, not a crash
    assert raises(lambda: compute({"a": "1/x"}, {"x": 0})), "zero-div not wrapped"

    # metric chaining across passes (declared out of order)
    out = compute({"c": "a + b", "a": "2", "b": "a * 3"}, {})
    assert out == {"c": 8.0, "a": 2.0, "b": 6.0}, out

    # constraint checking + margin
    cons = [
        {"id": "cap", "expr": "spend <= 100", "label": "budget", "owner": "finance"},
        {"id": "floor", "expr": "reserve >= 30", "label": "reserve", "owner": "finance"},
    ]
    v = check(cons, {"spend": 130, "reserve": 40})
    assert [c["id"] for c in v] == ["cap"], v
    assert v[0]["margin"] == 30.0, v[0]
    assert check(cons, {"spend": 90, "reserve": 40}) == []

    # boolean ops and comparison chains
    assert safe_eval("0.1 <= rate <= 0.19", {"rate": 0.15}) is True
    assert safe_eval("a and not b", {"a": True, "b": False}) is True

    print("calculator.py: all acceptance checks passed")


if __name__ == "__main__":
    demo()
