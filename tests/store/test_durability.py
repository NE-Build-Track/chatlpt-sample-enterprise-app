"""Migrations and the declared schema agree, and the generated docs are current."""

from pathlib import Path

from sqlalchemy import inspect

from chatlpt.docs_gen import generate
from chatlpt.store import SqlStore, current_revision, head_revision
from chatlpt.store.schema import metadata


async def test_migrated_database_matches_the_declared_schema(tmp_path: Path) -> None:
    store = await SqlStore.connect(f"sqlite+aiosqlite:///{tmp_path}/d.db")
    try:
        assert await current_revision(store.engine) == head_revision()
        async with store.engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync: {
                    t: {c["name"] for c in inspect(sync).get_columns(t)}
                    for t in inspect(sync).get_table_names()
                }
            )
    finally:
        await store.close()
    for table in metadata.sorted_tables:
        assert table.name in tables, (
            f"migration missing table {table.name}: add a migration in store/migrations/versions"
        )
        declared = {c.name for c in table.columns}
        assert declared == tables[table.name], (
            f"{table.name}: schema.py has {sorted(declared)} but the migrations create {sorted(tables[table.name])}. "
            "Add a migration and run `uv run chatlpt gen-docs`."
        )


def test_generated_docs_are_current() -> None:
    out = Path(__file__).resolve().parents[2] / "docs" / "generated"
    stale = generate(out, check=True)
    assert stale == [], f"docs/generated is stale ({stale}): run `uv run chatlpt gen-docs`"
