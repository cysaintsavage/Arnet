"""Owner dashboard and public site configuration. Admin checks are enforced by the route decorator on the server."""
from datetime import datetime, timedelta, timezone

from . import mailer, settings_store
from .config import env
from .core import ApiError, route
from .db import db, tx
from .tools_registry import public_tools


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


@route("/api/public/config", ["GET"], auth=None, body=None)
def public_config(ctx):
    s = settings_store.all_settings()
    ai = settings_store.effective_ai()
    return {
        "brand_name": s["brand_name"], "tagline": s["tagline"], "owner_name": s["owner_name"], "creator": s["creator"],
        "contact_email": s["contact_email"], "whatsapp": s["whatsapp"],
        "whatsapp_link": settings_store.whatsapp_link(s["whatsapp"], s["whatsapp_country_code"]),
        "registration_open": s["registration_open"] == "true",
        "ai_available": ai["configured"], "password_reset_available": mailer.configured(),
        "plans": {"free_daily_messages": int(s["free_daily_messages"]), "pro_daily_messages": int(s["pro_daily_messages"])},
        "payments_active": False,
    }


@route("/api/tools", ["GET"], auth=None, body=None)
def tools(ctx):
    return {"tools": public_tools()}


@route("/api/health", ["GET"], auth=None, body=None)
def health(ctx):
    try:
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}
    except Exception:
        raise ApiError(503, "Database unavailable.")


# ---------- admin ----------

@route("/api/admin/stats", ["GET"], auth="admin", body=None)
def stats(ctx):
    with db() as conn:
        one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
        daily = conn.execute(
            "SELECT substr(created_at,1,10) AS day, COUNT(*) AS requests, SUM(status='error') AS errors "
            "FROM ai_requests WHERE created_at >= ? GROUP BY day ORDER BY day", (_since(7),)).fetchall()
        avg = conn.execute("SELECT AVG(duration_ms) FROM ai_requests WHERE status = 'ok' AND created_at >= ?", (_since(1),)).fetchone()[0]
        return {
            "users_total": one("SELECT COUNT(*) FROM users"),
            "users_new_7d": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", _since(7)),
            "users_pro": one("SELECT COUNT(*) FROM users WHERE plan = 'pro'"),
            "users_disabled": one("SELECT COUNT(*) FROM users WHERE disabled = 1"),
            "conversations": one("SELECT COUNT(*) FROM conversations"),
            "messages": one("SELECT COUNT(*) FROM messages"),
            "documents": one("SELECT COUNT(*) FROM documents"),
            "images": one("SELECT COUNT(*) FROM images"),
            "requests_24h": one("SELECT COUNT(*) FROM ai_requests WHERE created_at >= ?", _since(1)),
            "errors_24h": one("SELECT COUNT(*) FROM ai_requests WHERE status = 'error' AND created_at >= ?", _since(1)),
            "avg_latency_ms_24h": int(avg) if avg else None,
            "daily": [dict(r) for r in daily],
        }


@route("/api/admin/users", ["GET"], auth="admin", body=None)
def users(ctx):
    q = (ctx.query.get("q") or "").strip()[:100]
    with db() as conn:
        base = ("SELECT u.id, u.email, u.name, u.role, u.plan, u.disabled, u.created_at, u.last_login, "
                "(SELECT COUNT(*) FROM ai_requests r WHERE r.user_id = u.id AND r.status = 'ok') AS requests FROM users u ")
        if q:
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = conn.execute(base + "WHERE u.email LIKE ? ESCAPE '\\' OR u.name LIKE ? ESCAPE '\\' ORDER BY u.id DESC LIMIT 200", (like, like)).fetchall()
        else:
            rows = conn.execute(base + "ORDER BY u.id DESC LIMIT 200").fetchall()
    return {"users": [dict(r) for r in rows]}


@route("/api/admin/users/{uid}", ["PATCH"], auth="admin")
def update_user(ctx):
    try:
        uid = int(ctx.params["uid"])
    except ValueError:
        raise ApiError(404, "User not found.")
    d = ctx.body
    changes: dict[str, object] = {}
    if "plan" in d:
        if d["plan"] not in ("free", "pro"):
            raise ApiError(400, "plan must be free or pro.")
        changes["plan"] = d["plan"]
    if "role" in d:
        if d["role"] not in ("user", "admin"):
            raise ApiError(400, "role must be user or admin.")
        changes["role"] = d["role"]
    if "disabled" in d:
        if not isinstance(d["disabled"], bool):
            raise ApiError(400, "disabled must be true or false.")
        changes["disabled"] = 1 if d["disabled"] else 0
    if not changes:
        raise ApiError(400, "Nothing to change.")
    if uid == ctx.user["id"] and ("role" in changes or "disabled" in changes):
        raise ApiError(400, "You cannot change your own role or disable your own account.")
    with db() as conn:
        with tx(conn):
            if not conn.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
                raise ApiError(404, "User not found.")
            sets = ", ".join(f"{k} = ?" for k in changes)  # keys come from the fixed list above, never from input
            conn.execute(f"UPDATE users SET {sets} WHERE id = ?", (*changes.values(), uid))
            if changes.get("disabled") == 1 or changes.get("role") == "user":
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
        row = conn.execute("SELECT id, email, name, role, plan, disabled FROM users WHERE id = ?", (uid,)).fetchone()
    return {"user": dict(row)}


@route("/api/admin/requests", ["GET"], auth="admin", body=None)
def requests_log(ctx):
    with db() as conn:
        rows = conn.execute(
            "SELECT r.id, r.kind, r.model, r.status, r.duration_ms, r.created_at, u.email FROM ai_requests r "
            "LEFT JOIN users u ON u.id = r.user_id ORDER BY r.id DESC LIMIT 100").fetchall()
    return {"requests": [dict(r) for r in rows]}


@route("/api/admin/errors", ["GET"], auth="admin", body=None)
def errors(ctx):
    with db() as conn:
        rows = conn.execute("SELECT id, source, message, created_at FROM error_log ORDER BY id DESC LIMIT 100").fetchall()
    return {"errors": [dict(r) for r in rows]}


@route("/api/admin/settings", ["GET"], auth="admin", body=None)
def get_settings(ctx):
    ai = settings_store.effective_ai()
    return {"settings": settings_store.all_settings(),
            "effective_ai": {"provider": ai["provider"], "model": ai["model"], "key_configured": ai["configured"]}}


@route("/api/admin/settings", ["PUT"], auth="admin")
def put_settings(ctx):
    try:
        s = settings_store.validate_and_save(ctx.body)
    except ValueError as e:
        raise ApiError(400, str(e))
    ai = settings_store.effective_ai()
    return {"settings": s, "effective_ai": {"provider": ai["provider"], "model": ai["model"], "key_configured": ai["configured"]}}


@route("/api/admin/health", ["GET"], auth="admin", body=None)
def admin_health(ctx):
    e = env()
    ai = settings_store.effective_ai()
    try:
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    def item(name, ok, detail_ok, detail_bad, optional=False):
        return {"name": name, "status": "ok" if ok else ("not_configured" if optional else "down"),
                "detail": detail_ok if ok else detail_bad}
    return {"services": [
        item("Database", db_ok, "SQLite is reachable.", "The database cannot be opened."),
        item("AI provider", ai["configured"], f"Key set. Provider {ai['provider']}, model {ai['model']}. (The key is not tested until a request is made.)",
             "AI_API_KEY is not set."),
        item("Image generation", bool(e.image_api_key), f"Key set, model {e.image_model}.", "IMAGE_API_KEY is not set.", optional=True),
        item("Web search", bool(e.search_api_key), "Key set.", "SEARCH_API_KEY is not set.", optional=True),
        item("Email (password reset)", mailer.configured(), "SMTP is configured.", "SMTP_HOST and SMTP_FROM are not set.", optional=True),
        {"name": "Payments", "status": "not_implemented",
         "detail": "Payment processing and webhook verification are not built. Plans are changed manually in the Users tab."},
    ]}
