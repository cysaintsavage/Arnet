"""Shared plumbing: route registry, auth lookup, errors, rate limiting."""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .config import env
from .db import db, now_iso
from .security import limiter, token_hash

COOKIE = "arnet_session"
SESSION_DAYS = 14


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Ctx:
    request: Request
    user: dict | None
    body: Any = None
    params: dict = field(default_factory=dict)
    query: dict = field(default_factory=dict)


ROUTES: list[Route] = []


def route(path: str, methods: list[str], auth: str | None = "user", body: str | None = "json") -> Callable:
    """auth: None (public), 'user' (signed in) or 'admin' (signed in and role == admin, checked in the database).
    body: 'json' (parsed, must be an object), 'raw' (bytes) or None."""

    def deco(fn: Callable) -> Callable:
        async def endpoint(request: Request) -> Response:
            user = await run_in_threadpool(current_user, request)
            if auth and not user:
                raise ApiError(401, "Please sign in.")
            if auth == "admin" and user["role"] != "admin":
                raise ApiError(403, "You do not have permission to do that.")
            data: Any = None
            if body == "json" and request.method in ("POST", "PUT", "PATCH", "DELETE"):
                raw = await request.body()
                if len(raw) > 2_000_000:
                    raise ApiError(413, "Request is too large.")
                if raw:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        raise ApiError(400, "Request body is not valid JSON.")
                    if not isinstance(data, dict):
                        raise ApiError(400, "Request body must be a JSON object.")
                else:
                    data = {}
            elif body == "raw":
                raw = await request.body()
                data = raw
            ctx = Ctx(request, user, data, dict(request.path_params), dict(request.query_params))
            result = await run_in_threadpool(fn, ctx)
            if isinstance(result, Response):
                return result
            return JSONResponse(result)

        ROUTES.append(Route(path, endpoint, methods=methods))
        return fn

    return deco


def client_ip(request: Request) -> str:
    if env().trust_proxy:
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()[:64]
    return request.client.host if request.client else "unknown"


def rate_limit(key: str, limit: int, window_s: int, message: str = "Too many requests. Please wait and try again.") -> None:
    if not limiter.check(key, limit, window_s):
        raise ApiError(429, message)


def current_user(request: Request) -> dict | None:
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    with db() as conn:
        row = conn.execute(
            "SELECT u.id, u.email, u.name, u.role, u.plan, u.disabled, u.created_at, s.expires_at "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?", (token_hash(tok),)).fetchone()
        if not row or row["expires_at"] < now_iso():
            return None
        if row["disabled"]:
            return None
        return {k: row[k] for k in ("id", "email", "name", "role", "plan", "created_at")}


def log_error(source: str, message: str) -> None:
    """Record a server-side problem for the owner's error monitor. Messages are truncated; never pass secrets."""
    try:
        with db() as conn:
            conn.execute("INSERT INTO error_log(source, message) VALUES (?, ?)", (source[:60], message[:500]))
            conn.execute("DELETE FROM error_log WHERE id < (SELECT MAX(id) FROM error_log) - 2000")
    except Exception:
        pass


def expiry_iso(days: int = SESSION_DAYS, minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days, minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_start_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def need_str(d: dict, key: str, max_len: int, required: bool = True) -> str:
    v = d.get(key, "")
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ApiError(400, f"{key} must be text.")
    v = v.strip()
    if required and not v:
        raise ApiError(400, f"{key} is required.")
    if len(v) > max_len:
        raise ApiError(400, f"{key} is too long (maximum {max_len} characters).")
    return v
