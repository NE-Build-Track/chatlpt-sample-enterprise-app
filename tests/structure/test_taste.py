"""Taste invariants (docs/design-docs/core-beliefs.md). Each failure says how to fix it."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "chatlpt"
MAX_LINES = 500
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
MONEY_MODULES = ("contracts/common.py", "contracts/billing.py")


def sources() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py") if "migrations/versions" not in str(path))


def rel(path: Path) -> str:
    return str(path.relative_to(SRC))


@pytest.mark.parametrize("path", sources(), ids=rel)
def test_modules_explain_themselves(path: Path) -> None:
    tree = ast.parse(path.read_text())
    if not tree.body:
        return
    assert ast.get_docstring(tree), f"{rel(path)} needs a module docstring saying what it owns and why."


@pytest.mark.parametrize("path", sources(), ids=rel)
def test_files_stay_small(path: Path) -> None:
    lines = len(path.read_text().splitlines())
    assert lines <= MAX_LINES, f"{rel(path)} has {lines} lines (> {MAX_LINES}). Split it by responsibility."


@pytest.mark.parametrize("path", sources(), ids=rel)
def test_logging_is_structured(path: Path) -> None:
    for node in ast.walk(ast.parse(path.read_text())):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in LOG_METHODS or not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id not in ("_LOG", "logger", "log"):
            continue
        extra = next((kw.value for kw in node.keywords if kw.arg == "extra"), None)
        has_event = isinstance(extra, ast.Dict) and any(
            isinstance(key, ast.Constant) and key.value == "event" for key in extra.keys
        )
        assert has_event, (
            f"{rel(path)}:{node.lineno} logs without extra={{'event': 'domain.action', ...}}. "
            "Every log line carries a queryable event name (chatlpt/runtime/logging.py)."
        )


@pytest.mark.parametrize("path", sources(), ids=rel)
def test_no_print_outside_the_cli(path: Path) -> None:
    if rel(path) == "cli.py":
        return
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            pytest.fail(f"{rel(path)}:{node.lineno} uses print(); log a structured event instead.")


@pytest.mark.parametrize("module", MONEY_MODULES)
def test_money_is_never_a_float(module: str) -> None:
    for node in ast.walk(ast.parse((SRC / module).read_text())):
        if isinstance(node, ast.Name) and node.id == "float":
            pytest.fail(
                f"{module}:{node.lineno} uses float. Money and prices are Decimal (exact) everywhere."
            )


def test_no_secret_reaches_a_log_or_response_by_name() -> None:
    """Keys that look like secrets never appear as log ``extra`` fields (docs/SECURITY.md#rules)."""
    bad = ("token", "secret", "password", "api_key", "payment_key")
    for path in sources():
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in LOG_METHODS:
                continue
            extra = next((kw.value for kw in node.keywords if kw.arg == "extra"), None)
            if not isinstance(extra, ast.Dict):
                continue
            for key in extra.keys:
                name = str(key.value).lower() if isinstance(key, ast.Constant) else ""
                if name and not name.endswith("_tokens") and any(word in name for word in bad):
                    pytest.fail(
                        f"{rel(path)}:{node.lineno} logs a field named {key.value!r}. Log an id or a hash, "
                        "never a credential (docs/SECURITY.md#rules)."
                    )
