"""Safe arithmetic for verification: + - * / ** and parentheses on numbers. No eval().

All arithmetic behind a verdict happens here (or in numbers.py), never in the model:
the Tier 2 agent's `calculate` tool calls this, and every result is logged.
"""

from __future__ import annotations

import ast
import operator

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
MAX_LEN = 200


class CalcError(ValueError):
    pass


def calculate(expression: str) -> float:
    """Evaluate a plain arithmetic expression, e.g. "(1234.5 - 1100) / 1100 * 100"."""
    if not isinstance(expression, str) or len(expression) > MAX_LEN:
        raise CalcError("expression must be a string of at most 200 characters")
    expr = expression.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CalcError(f"not an arithmetic expression: {expression!r}") from exc
    return float(_eval(tree.body))


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 10:
            raise CalcError("exponent too large")
        try:
            return _OPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalcError("division by zero") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise CalcError("only numbers, + - * / ** and parentheses are allowed")


def pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return (new - old) / abs(old) * 100.0
