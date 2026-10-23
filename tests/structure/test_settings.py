"""Settings are values (docs/exec-plans/completed/plan-08-dependency-injection.md).

Only config.py reads the environment (``Settings.from_env``; builder-core's ``EngineSettings.from_env``
reads ``LPB_*``). Everything else receives settings, so tests build them in code instead of setting
variables, and the composition root decides where configuration comes from.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "chatlpt"
ENV_NAMES = {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}
ALLOWED = {SRC / "config.py"}


def env_reads(path: Path) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        os_attribute = (
            isinstance(node, ast.Attribute)
            and node.attr in ENV_NAMES
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        )
        from_os = (
            isinstance(node, ast.ImportFrom)
            and node.module == "os"
            and any(alias.name in ENV_NAMES for alias in node.names)
        )
        if os_attribute or from_os:
            lines.append(node.lineno)
    return lines


def test_only_config_reads_the_environment() -> None:
    found = [
        f"{path.relative_to(SRC)}:{line}"
        for path in sorted(SRC.rglob("*.py"))
        if path not in ALLOWED
        for line in env_reads(path)
    ]
    assert not found, (
        f"the environment is read outside config.py: {found}. Add a field to Settings (CHATLPT_*) or take "
        "an EngineSettings (LPB_*) as a parameter. cli.py, the composition root, builds both: "
        "Settings.from_env() and runtime.engine_settings_from_env()."
    )
