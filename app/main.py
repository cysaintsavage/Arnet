"""ARNET AI application entry point: uvicorn app.main:app"""
import os
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import routes_admin, routes_auth, routes_chat  # noqa: F401  (importing registers the routes)
from .core import ROUTES, ApiError, log_error
from .db import migrate

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


class Guard(BaseHTTPMiddleware):
    """CSRF defence for the JSON API plus security headers on every response."""

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            bad_origin = bool(origin) and urlparse(origin).netloc != request.headers.get("host", "")
            if bad_origin or request.headers.get("x-requested-with") != "arnet-web":
                return JSONResponse({"error": "Request blocked."}, status_code=403)
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
        if "Content-Security-Policy" not in h:  # the preview route sets its own, stricter policy
            h["Content-Security-Policy"] = CSP
            h["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        return response


async def api_error(request: Request, exc: ApiError):
    return JSONResponse({"error": exc.message}, status_code=exc.status)


async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        msg = {404: "Not found.", 405: "Method not allowed."}.get(exc.status_code, "Request failed.")
        return JSONResponse({"error": msg}, status_code=exc.status_code)
    return Response("Not found", status_code=exc.status_code, media_type="text/plain")


async def server_error(request: Request, exc: Exception):
    log_error("server", f"{request.method} {request.url.path}: {type(exc).__name__}: {str(exc)[:200]}")
    return JSONResponse({"error": "Something went wrong on the server."}, status_code=500)


async def index(request: Request):
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})


def create_app() -> Starlette:
    migrate()
    return Starlette(
        routes=[Route("/", index), *ROUTES, Mount("/static", StaticFiles(directory=STATIC_DIR), name="static")],
        middleware=[__import__("starlette.middleware", fromlist=["Middleware"]).Middleware(Guard)],
        exception_handlers={ApiError: api_error, HTTPException: http_error, Exception: server_error},
    )


app = create_app()
