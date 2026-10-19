"""``create_app``: routes, error mapping, health, and the static React bundle with SPA fallback."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from chatlpt.contracts import AppHealth
from chatlpt.errors import AppError, ChatUnavailable
from chatlpt.http.routes_admin import admin_router
from chatlpt.http.routes_auth import auth_router
from chatlpt.http.routes_chat import chat_router
from chatlpt.http.sessions import Sessions, current_user_dependency
from chatlpt.runtime import Application, package_version


def create_app(app: Application, *, manage_lifecycle: bool = True) -> FastAPI:
    secret = app.settings.session_secret
    if secret is None or not secret.get_secret_value():
        raise AppError("CHATLPT_SESSION_SECRET is required to serve (chatlpt gen-secret)")
    sessions = Sessions(
        secret.get_secret_value(),
        ttl_s=app.settings.session_ttl_hours * 3600,
        secure=app.settings.secure_cookies,
    )
    current_user = current_user_dependency(app, sessions)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if manage_lifecycle:
            await app.start()
        try:
            yield
        finally:
            if manage_lifecycle:
                await app.stop()

    api = FastAPI(title="ChatLPT", version=package_version(), lifespan=lifespan)
    _install_error_handlers(api)

    @api.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/readyz", response_model=AppHealth)
    async def readyz() -> JSONResponse:
        health = await app.health()
        return JSONResponse(health.model_dump(mode="json"), status_code=200 if health.ready else 503)

    api.include_router(auth_router(app, sessions, current_user))
    api.include_router(chat_router(app, current_user))
    api.include_router(admin_router(app, current_user))
    _mount_static(api, Path(app.settings.static_dir))
    return api


def _install_error_handlers(api: FastAPI) -> None:
    @api.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after_s)} if isinstance(exc, ChatUnavailable) else None
        return JSONResponse(
            {"error": str(exc), "type": type(exc).__name__}, status_code=exc.status_code, headers=headers
        )


def _mount_static(api: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    if not index.exists():
        return  # API-only (the UI is not built); /readyz still answers
    if (static_dir / "assets").is_dir():
        api.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @api.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
