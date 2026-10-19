"""UI layer: FastAPI routes, server-sent events and the static React bundle. Thin over the Application."""

from chatlpt.http.app import create_app

__all__ = ["create_app"]
