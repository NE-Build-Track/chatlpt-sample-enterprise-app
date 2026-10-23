"""ChatLPT uses only builder-core's public API (builder-core decision: the embedding surface is the public API).

The package root, ``livepeer_builder.api`` (the facade Protocols), ``livepeer_builder.protocols`` (the
ports we implement or decorate) and ``livepeer_builder.testing`` (tests only). A name builder-core does
not export is an internal it may change in any release; if we need one, it should be exported there.
"""

import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = {"livepeer_builder", "livepeer_builder.api", "livepeer_builder.protocols"}
TESTS_ONLY = {"livepeer_builder.testing"}
FILES = sorted((ROOT / "src" / "chatlpt").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py"))


def exported(module: str) -> set[str]:
    loaded = importlib.import_module(module)
    names = getattr(loaded, "__all__", None)
    return set(names) if names is not None else {n for n in vars(loaded) if not n.startswith("_")}


def private_uses(path: Path) -> list[str]:
    allowed = PUBLIC | (TESTS_ONLY if path.is_relative_to(ROOT / "tests") else set())
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module, names = node.module, [alias.name for alias in node.names]
        elif isinstance(node, ast.Import):
            module, names = (
                next((a.name for a in node.names if a.name.startswith("livepeer_builder")), ""),
                [],
            )
        else:
            continue
        if not module.startswith("livepeer_builder"):
            continue
        if module not in allowed:
            found.append(f"{node.lineno}: {module}")
        elif hidden := sorted(set(names) - exported(module)):
            found.append(f"{node.lineno}: {', '.join(hidden)} from {module}")
    return found


@pytest.mark.parametrize("path", FILES, ids=lambda path: str(path.relative_to(ROOT)))
def test_only_the_public_engine_api_is_imported(path: Path) -> None:
    found = private_uses(path)
    assert not found, (
        f"{path.relative_to(ROOT)} imports builder-core internals: {found}. Import from livepeer_builder "
        "(or .api, .protocols; .testing in tests). If the name is not exported, it belongs in builder-core's "
        "public API first."
    )
