
import ast
import math
import operator

MAX_NODES = 60
MAX_ABS = 1e15
MAX_POW_EXPONENT = 64
MAX_PAREN_DEPTH = 30

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "log": math.log,
    "log10": math.log10,
    "ceil": math.ceil,
    "floor": math.floor,
}

_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


class CalcError(Exception):
    """The expression is not allowed or cannot be computed."""


def safe_eval(expression: str) -> int | float:
    """Safely evaluate arithmetic expressions using Python's AST.

    Allowed:
        - Numbers
        - Arithmetic operators: +, -, *, /, //, %, **
        - Parentheses
        - Selected mathematical functions
        - Mathematical constants pi and e

    Disallowed:
        - Arbitrary Python code
        - Imports and attribute access
        - Strings, lists and dictionaries
        - Excessive expression complexity
        - Excessive parentheses nesting
    """

    if len(expression) > 200:
        raise CalcError("The expression is too long")

    # Prevent excessive parentheses nesting.
    # AST parsing removes redundant parentheses, so MAX_NODES
    # alone cannot detect deeply nested expressions.
    depth = 0

    for char in expression:
        if char == "(":
            depth += 1

            if depth > MAX_PAREN_DEPTH:
                raise CalcError("Too many nested parentheses")

        elif char == ")":
            depth -= 1

            if depth < 0:
                raise CalcError("Unbalanced parentheses")

    if depth != 0:
        raise CalcError("Unbalanced parentheses")

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise CalcError("Not a valid arithmetic expression")

    nodes = {"count": 0}

    def check(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise CalcError("The result is not finite")

        if abs(value) > MAX_ABS:
            raise CalcError("The result is too large")

        return value

    def evaluate(node):
        nodes["count"] += 1

        if nodes["count"] > MAX_NODES:
            raise CalcError("The expression is too complex")

        if isinstance(node, ast.Expression):
            return evaluate(node.body)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)
            ):
                raise CalcError("Only numbers are allowed")

            return check(node.value)

        if isinstance(node, ast.BinOp):
            op = type(node.op)

            if op not in _BINARY:
                raise CalcError("Operator not allowed (use ** for powers)")

            left = evaluate(node.left)
            right = evaluate(node.right)

            if op is ast.Pow and abs(right) > MAX_POW_EXPONENT:
                raise CalcError("The exponent is too large")

            try:
                return check(_BINARY[op](left, right))

            except ZeroDivisionError:
                raise CalcError("Division by zero")

            except (OverflowError, ValueError):
                raise CalcError("The result cannot be represented")

        if isinstance(node, ast.UnaryOp):
            op = type(node.op)

            if op not in _UNARY:
                raise CalcError("Operator not allowed")

            return check(_UNARY[op](evaluate(node.operand)))

        if isinstance(node, ast.Name):
            if node.id in _CONSTANTS:
                return _CONSTANTS[node.id]

            raise CalcError(f"Unknown name '{node.id}'")

        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in _FUNCTIONS
                or node.keywords
                or not node.args
                or len(node.args) > 5
            ):
                raise CalcError("Function call not allowed")

            values = [evaluate(a) for a in node.args]

            try:
                return check(_FUNCTIONS[node.func.id](*values))

            except (TypeError, ValueError, OverflowError):
                raise CalcError("Invalid function arguments")

        raise CalcError("Unsupported syntax")

    return evaluate(tree)