"""``chatlpt``: operator commands. Every command reads CHATLPT_* (and the engine's LPB_*) settings.

chatlpt migrate            apply packaged migrations
chatlpt revision           show the database revision and the package head
chatlpt gen-secret         print a new CHATLPT_SESSION_SECRET
chatlpt smoke              migrate, start, health-check, stop (install check)
chatlpt serve              run the app (API + static UI)
chatlpt gen-docs [--check] regenerate docs/generated (openapi.json, db-schema.md)
chatlpt make-admin EMAIL [--allow-unverified]   grant admin (the only way, D26)
chatlpt revoke-admin EMAIL                      take admin away
"""

import argparse
import asyncio
import json
import logging
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from chatlpt.config import Settings
from chatlpt.errors import AppError
from chatlpt.runtime import Application, package_version
from chatlpt.runtime.logging import configure_logging
from chatlpt.store import SqlStore, current_revision, head_revision, upgrade


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(asyncio.run(args.handler(args)) or 0)
    except AppError as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chatlpt", description="ChatLPT operator commands")
    parser.add_argument("--version", action="version", version=package_version())
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    def command(name: str, handler: Any, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)
        return sub

    command("migrate", _migrate, "apply packaged migrations")
    command("revision", _revision, "show database and package schema revisions")
    command("gen-secret", _gen_secret, "print a new CHATLPT_SESSION_SECRET")
    command("smoke", _smoke, "migrate/start/health/stop check")
    command("serve", _serve, "run the app")
    grant = command("make-admin", _make_admin, "grant admin rights to an account (the only way, D26)")
    grant.add_argument("email")
    grant.add_argument(
        "--allow-unverified",
        action="store_true",
        help="also for a password-only account, whose email nobody has proven",
    )
    command("revoke-admin", _revoke_admin, "take admin rights away").add_argument("email")
    docs = command("gen-docs", _gen_docs, "regenerate docs/generated")
    docs.add_argument("--out", type=Path, default=Path("docs/generated"))
    docs.add_argument("--check", action="store_true", help="fail if the committed files are stale")
    return parser


def _emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


async def _migrate(_: argparse.Namespace) -> None:
    store = await SqlStore.connect(Settings.from_env().database_url, migrate=False)
    try:
        await upgrade(store.engine)
        _emit({"revision": await current_revision(store.engine)})
    finally:
        await store.close()


async def _revision(_: argparse.Namespace) -> None:
    store = await SqlStore.connect(Settings.from_env().database_url, migrate=False)
    try:
        _emit({"database": await current_revision(store.engine), "package": head_revision()})
    finally:
        await store.close()


async def _make_admin(args: argparse.Namespace) -> None:
    await _set_admin(args.email, True, allow_unverified=args.allow_unverified)


async def _revoke_admin(args: argparse.Namespace) -> None:
    await _set_admin(args.email, False)


async def _set_admin(email: str, is_admin: bool, *, allow_unverified: bool = False) -> None:
    from chatlpt.adapters.clock import SystemClock
    from chatlpt.adapters.passwords import Argon2Hasher
    from chatlpt.services.auth import AuthService

    settings = Settings.from_env()
    store = await SqlStore.connect(settings.database_url, migrate=settings.auto_migrate)
    try:
        auth = AuthService(store, Argon2Hasher(), SystemClock(), allow_signup=settings.allow_signup)
        user = await auth.set_admin(email, is_admin, allow_unverified=allow_unverified)
        _emit({"email": user.email, "is_admin": user.is_admin, "email_verified": user.email_verified})
    finally:
        await store.close()


async def _gen_secret(_: argparse.Namespace) -> None:
    print(secrets.token_urlsafe(48))


async def _smoke(_: argparse.Namespace) -> int:
    settings = Settings.from_env()
    configure_logging(json_lines=settings.log_json)
    app = await Application.from_settings(settings)
    await app.start()
    try:
        health = await app.health()
        _emit(health.model_dump(mode="json"))
        return 0 if health.ready else 1
    finally:
        await app.stop()


async def _serve(_: argparse.Namespace) -> None:
    import uvicorn

    from chatlpt.http import create_app

    settings = Settings.from_env()
    configure_logging(json_lines=settings.log_json)
    app = await Application.from_settings(settings)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(app),
            host=settings.http_host,
            port=settings.http_port,
            log_config=None,
            access_log=False,
        )
    )
    await server.serve()


async def _gen_docs(args: argparse.Namespace) -> int:
    from chatlpt.docs_gen import generate

    logging.getLogger().setLevel(logging.WARNING)
    stale = generate(args.out, check=args.check)
    if args.check and stale:
        print(f"stale generated docs: {', '.join(stale)}; run `uv run chatlpt gen-docs`", file=sys.stderr)
        return 1
    _emit({"written": sorted(p.name for p in args.out.iterdir())})
    return 0
