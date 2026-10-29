"""Registration, login, sessions, password reset and the signed-in user's own account."""
import os
import shutil

from starlette.responses import JSONResponse

from . import mailer, settings_store
from .config import env
from .core import (COOKIE, EMAIL_RE, SESSION_DAYS, ApiError, client_ip, expiry_iso, log_error, need_str, rate_limit,
                   route, today_start_iso)
from .db import db, now_iso, tx
from .security import DUMMY_HASH, hash_password, new_token, token_hash, verify_password


def _session_response(conn, user_id: int, payload: dict) -> JSONResponse:
    tok = new_token()
    conn.execute("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                 (token_hash(tok), user_id, expiry_iso(SESSION_DAYS)))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
    resp = JSONResponse(payload)
    resp.set_cookie(COOKIE, tok, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                    secure=env().cookie_secure, path="/")
    return resp


def _check_password(pw: str, email: str = "") -> None:
    if not isinstance(pw, str) or len(pw) < 8:
        raise ApiError(400, "Password must be at least 8 characters.")
    if len(pw) > 200:
        raise ApiError(400, "Password is too long.")
    if email and pw.lower() == email.lower():
        raise ApiError(400, "Password must not be the same as your email.")


def _public_user(u) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"], "plan": u["plan"],
            "created_at": u["created_at"]}


@route("/api/auth/register", ["POST"], auth=None)
def register(ctx):
    ip = client_ip(ctx.request)
    rate_limit(f"register:{ip}", 5, 3600, "Too many sign-ups from this network. Try again later.")
    if settings_store.get("registration_open") != "true":
        raise ApiError(403, "Registration is currently closed.")
    email = need_str(ctx.body, "email", 254).lower()
    if not EMAIL_RE.match(email):
        raise ApiError(400, "Enter a valid email address.")
    pw = ctx.body.get("password", "")
    _check_password(pw, email)
    name = need_str(ctx.body, "name", 60, required=False)
    pw_hash = hash_password(pw)
    with db() as conn:
        try:
            with tx(conn):
                cur = conn.execute("INSERT INTO users(email, password_hash, name) VALUES (?, ?, ?)", (email, pw_hash, name))
                uid = cur.lastrowid
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ApiError(409, "That email can't be registered. Try signing in instead.")
            raise
        user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return _session_response(conn, uid, {"user": _public_user(user)})


@route("/api/auth/login", ["POST"], auth=None)
def login(ctx):
    ip = client_ip(ctx.request)
    email = need_str(ctx.body, "email", 254).lower()
    pw = ctx.body.get("password", "")
    if not isinstance(pw, str) or not pw or len(pw) > 200:
        raise ApiError(400, "Enter your email and password.")
    rate_limit(f"login-ip:{ip}", 30, 600, "Too many sign-in attempts. Try again in a few minutes.")
    rate_limit(f"login:{email}", 8, 600, "Too many sign-in attempts. Try again in a few minutes.")
    with db() as conn:
        u = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        ok = verify_password(pw, u["password_hash"] if u else DUMMY_HASH)
        if not u or not ok or u["disabled"]:
            raise ApiError(401, "Incorrect email or password.")
        conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso(), u["id"]))
        return _session_response(conn, u["id"], {"user": _public_user(u)})


@route("/api/auth/logout", ["POST"], auth=None, body=None)
def logout(ctx):
    tok = ctx.request.cookies.get(COOKIE)
    if tok:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(tok),))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@route("/api/auth/forgot", ["POST"], auth=None)
def forgot(ctx):
    ip = client_ip(ctx.request)
    rate_limit(f"forgot:{ip}", 5, 3600)
    email = need_str(ctx.body, "email", 254).lower()
    rate_limit(f"forgot-email:{email}", 3, 3600)
    if not mailer.configured():
        raise ApiError(503, "Password reset by email is not set up on this server. Contact the site owner.")
    with db() as conn:
        u = conn.execute("SELECT id, email, disabled FROM users WHERE email = ?", (email,)).fetchone()
        if u and not u["disabled"]:
            tok = new_token()
            conn.execute("INSERT INTO reset_tokens(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                         (token_hash(tok), u["id"], expiry_iso(0, 30)))
            link = f"{env().app_base_url}/#/reset?token={tok}"
            try:
                mailer.send(u["email"], "Reset your ARNET AI password",
                            f"Use this link within 30 minutes to choose a new password:\n\n{link}\n\n"
                            "If you did not ask for this, you can ignore this email.")
            except Exception as e:
                log_error("mailer", f"{type(e).__name__}: {e}")
    return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}


@route("/api/auth/reset", ["POST"], auth=None)
def reset(ctx):
    rate_limit(f"reset:{client_ip(ctx.request)}", 10, 3600)
    tok = need_str(ctx.body, "token", 200)
    pw = ctx.body.get("password", "")
    _check_password(pw)
    pw_hash = hash_password(pw)
    with db() as conn:
        with tx(conn):
            r = conn.execute("SELECT * FROM reset_tokens WHERE token_hash = ?", (token_hash(tok),)).fetchone()
            if not r or r["used"] or r["expires_at"] < now_iso():
                raise ApiError(400, "This reset link is invalid or has expired. Request a new one.")
            conn.execute("UPDATE reset_tokens SET used = 1 WHERE token_hash = ?", (r["token_hash"],))
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, r["user_id"]))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (r["user_id"],))
    return {"ok": True}


# ---------- the signed-in user's own account ----------

def _limits_for(user: dict) -> dict:
    s = settings_store.all_settings()
    if user["role"] == "admin":
        return {"messages": None, "images": None}
    p = user["plan"]
    return {"messages": int(s[f"{p}_daily_messages"]), "images": int(s[f"{p}_daily_images"])}


def usage_today(conn, user_id: int, kind: str) -> int:
    return conn.execute("SELECT COUNT(*) c FROM ai_requests WHERE user_id = ? AND kind = ? AND created_at >= ? AND status != 'error'",
                        (user_id, kind, today_start_iso())).fetchone()["c"]


def limits_for(user: dict) -> dict:
    return _limits_for(user)


@route("/api/me", ["GET"])
def me(ctx):
    return {"user": ctx.user}


@route("/api/me", ["PATCH"])
def update_me(ctx):
    name = need_str(ctx.body, "name", 60, required=False)
    with db() as conn:
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, ctx.user["id"]))
    return {"user": {**ctx.user, "name": name}}


@route("/api/me/password", ["POST"])
def change_password(ctx):
    rate_limit(f"pwchange:{ctx.user['id']}", 6, 3600)
    cur, new = ctx.body.get("current", ""), ctx.body.get("new", "")
    _check_password(new, ctx.user["email"])
    with db() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (ctx.user["id"],)).fetchone()
        if not isinstance(cur, str) or not verify_password(cur, row["password_hash"]):
            raise ApiError(400, "Your current password is incorrect.")
        keep = token_hash(ctx.request.cookies.get(COOKIE, ""))
        with tx(conn):
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), ctx.user["id"]))
            conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (ctx.user["id"], keep))
    return {"ok": True}


@route("/api/me/usage", ["GET"])
def my_usage(ctx):
    with db() as conn:
        msgs = usage_today(conn, ctx.user["id"], "chat")
        imgs = usage_today(conn, ctx.user["id"], "image")
        total = conn.execute("SELECT COUNT(*) c FROM ai_requests WHERE user_id = ? AND status = 'ok'", (ctx.user["id"],)).fetchone()["c"]
        convs = conn.execute("SELECT COUNT(*) c FROM conversations WHERE user_id = ?", (ctx.user["id"],)).fetchone()["c"]
    lim = _limits_for(ctx.user)
    return {"plan": ctx.user["plan"], "messages_today": msgs, "messages_limit": lim["messages"],
            "images_today": imgs, "images_limit": lim["images"], "total_requests": total, "conversations": convs}


@route("/api/me", ["DELETE"])
def delete_me(ctx):
    rate_limit(f"delete:{ctx.user['id']}", 5, 3600)
    pw = ctx.body.get("password", "")
    uid = ctx.user["id"]
    with db() as conn:
        row = conn.execute("SELECT password_hash, role FROM users WHERE id = ?", (uid,)).fetchone()
        if not isinstance(pw, str) or not verify_password(pw, row["password_hash"]):
            raise ApiError(400, "Your password is incorrect.")
        if row["role"] == "admin":
            n = conn.execute("SELECT COUNT(*) c FROM users WHERE role = 'admin' AND disabled = 0").fetchone()["c"]
            if n <= 1:
                raise ApiError(400, "You are the only administrator. Make another user an administrator before deleting this account.")
        files = [r["file_name"] for r in conn.execute("SELECT file_name FROM images WHERE user_id = ?", (uid,))]
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))  # cascades to sessions, chats, documents, images, previews
    img_dir = os.path.join(env().data_dir, "images")
    for f in files:
        try:
            os.remove(os.path.join(img_dir, os.path.basename(f)))
        except OSError:
            pass
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp
