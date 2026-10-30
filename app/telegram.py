"""Telegram bot for ARNET AI.

People message the bot in a private chat. A chat must first be linked to an ARNET AI account with a one-time code made on
the website (Account, Connect Telegram). After that the bot uses the same chat engine as the website, so the account's plan,
daily limits, usage statistics and saved conversations all apply.

Two ways to receive messages (use one):
  webhook  Telegram calls POST /telegram/webhook on your HTTPS domain.  python -m app.cli telegram-webhook
  polling  A process asks Telegram for new messages (no domain needed).  python -m app.cli telegram-poll

Secrets (bot token, webhook secret) come from environment variables and are never logged or sent to the browser.
"""
import hmac
import html
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from .config import env
from .core import ApiError, log_error, rate_limit, route, expiry_iso
from .db import db, now_iso, tx
from .routes_auth import limits_for, usage_today
from .routes_chat import start_chat
from .security import token_hash
from .tools_registry import BY_ID, TOOLS, availability

CODE_ALPHABET = "9254988273:AAG0aDvXoTLpVijRZaGMbS1YIYaqq1Lqpxw"  # no 0/O/1/I
CODE_LEN = 8
CODE_MINUTES = 10
MSG_LIMIT = 3500  # Telegram allows 4096 characters; leave room for formatting

COMMANDS = [
    ("help", "How to use ARNET AI"),
    ("link", "Connect your ARNET AI account"),
    ("new", "Start a new conversation"),
    ("tools", "List available tools"),
    ("tool", "Switch tool, for example /tool writing"),
    ("usage", "Messages used today"),
    ("unlink", "Disconnect this chat"),
]


# ---------- Telegram HTTP API ----------

class TelegramError(Exception):
    def __init__(self, description: str, code: int = 0):
        super().__init__(description)
        self.description = description
        self.code = code


def configured() -> bool:
    return bool(env().telegram_token)


def api(method: str, params: dict | None = None, timeout: int = 40):
    """Call a Bot API method and return its `result`. Error text never contains the token or the request URL."""
    e = env()
    if not e.telegram_token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is not set.")
    req = urllib.request.Request(f"{e.telegram_api_base}/bot{e.telegram_token}/{method}",
                                 data=json.dumps(params or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as ex:
        try:
            desc = str(json.loads(ex.read(2000)).get("description") or "")
        except Exception:
            desc = ""
        raise TelegramError(desc or f"HTTP {ex.code}", ex.code)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as ex:
        raise TelegramError(f"Could not reach Telegram ({type(ex).__name__}).")
    if not isinstance(data, dict) or not data.get("ok"):
        raise TelegramError(str((data or {}).get("description") or "Telegram refused the request."))
    return data.get("result")


_username_cache: list[str] = []


def bot_username() -> str:
    e = env()
    if e.telegram_username:
        return e.telegram_username
    if not e.telegram_token:
        return ""
    if not _username_cache:
        try:
            _username_cache.append(str(api("getMe", timeout=5).get("username") or ""))
        except TelegramError:
            return ""
    return _username_cache[0]


def register_commands() -> None:
    api("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMMANDS]})


# ---------- formatting: model Markdown to Telegram HTML ----------

_FENCE = re.compile(r"```[ \t]*([\w+#.-]*)[ \t]*\n?(.*?)(?:```|\Z)", re.S)


def _inline(s: str) -> str:
    out = []
    for part in re.split(r"(`[^`\n]+`)", s):
        if len(part) > 2 and part.startswith("`") and part.endswith("`"):
            out.append("<code>" + html.escape(part[1:-1], quote=False) + "</code>")
            continue
        t = html.escape(part, quote=False)
        t = re.sub(r"(?m)^#{1,6}[ \t]+(.+)$", r"<b>\1</b>", t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
                   lambda m: '<a href="' + m.group(2).replace('"', "%22") + '">' + m.group(1) + "</a>", t)
        out.append(t)
    return "".join(out)


def to_html(text: str) -> str:
    """Only <b>, <code>, <pre> and <a href=http(s)> are ever produced; everything else is escaped."""
    out, pos = [], 0
    for m in _FENCE.finditer(text):
        out.append(_inline(text[pos:m.start()]))
        lang = html.escape(m.group(1), quote=True)
        cls = f' class="language-{lang}"' if lang else ""
        out.append(f"<pre><code{cls}>" + html.escape(m.group(2).rstrip("\n"), quote=False) + "</code></pre>")
        pos = m.end()
    out.append(_inline(text[pos:]))
    return "".join(out)


def split_message(text: str, limit: int = MSG_LIMIT) -> list[str]:
    """Cut long text into pieces under Telegram's size limit, closing and reopening code blocks across pieces."""
    lines: list[str] = []
    for line in text.split("\n"):
        while len(line) > 3000:
            lines.append(line[:3000])
            line = line[3000:]
        lines.append(line)
    pieces: list[str] = []
    cur, in_fence, fence_open = "", False, ""
    for line in lines:
        if cur and len(cur) + len(line) + 1 > limit - (4 if in_fence else 0):
            if in_fence:
                cur += "\n```"
            pieces.append(cur)
            cur = fence_open if in_fence else ""
        cur = (cur + "\n" + line) if cur else line
        if line.strip().startswith("```"):
            in_fence = not in_fence
            fence_open = line.strip() if in_fence else ""
    if cur.strip():
        pieces.append(cur)
    return pieces or [""]


def send_plain(chat_id: int, text: str) -> None:
    try:
        api("sendMessage", {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True})
    except TelegramError as e:
        if e.code != 403:  # 403 means the person blocked the bot; nothing to do
            log_error("telegram", f"send failed: {e.description[:150]}")


def send_answer(chat_id: int, text: str) -> None:
    """Send a model answer with formatting; if Telegram rejects the formatting, resend that piece as plain text."""
    for piece in split_message(text):
        if not piece.strip():
            continue
        try:
            api("sendMessage", {"chat_id": chat_id, "text": to_html(piece), "parse_mode": "HTML", "disable_web_page_preview": True})
        except TelegramError as e:
            if e.code == 400:
                send_plain(chat_id, piece)
            else:
                if e.code != 403:
                    log_error("telegram", f"send failed: {e.description[:150]}")
                return


class _Typing:
    """Shows 'typing...' in the chat while the answer is being written."""

    def __init__(self, chat_id: int):
        self.chat_id, self.stop = chat_id, threading.Event()

    def __enter__(self):
        def loop():
            while not self.stop.is_set():
                try:
                    api("sendChatAction", {"chat_id": self.chat_id, "action": "typing"}, timeout=10)
                except TelegramError:
                    pass
                self.stop.wait(4.5)
        threading.Thread(target=loop, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.stop.set()


# ---------- account linking ----------

def _make_code(user_id: int) -> str:
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
    with db() as conn:
        with tx(conn):
            conn.execute("DELETE FROM telegram_link_codes WHERE user_id = ? OR expires_at < ?", (user_id, now_iso()))
            conn.execute("INSERT INTO telegram_link_codes(code_hash, user_id, expires_at) VALUES (?, ?, ?)",
                         (token_hash(code), user_id, expiry_iso(days=0, minutes=CODE_MINUTES)))
    return code


def _get_link(chat_id: int):
    with db() as conn:
        return conn.execute("SELECT u.id, u.email, u.name, u.role, u.plan, u.disabled, u.created_at, "
                            "l.conversation_id, l.tool FROM telegram_links l JOIN users u ON u.id = l.user_id "
                            "WHERE l.chat_id = ?", (chat_id,)).fetchone()


def _redeem(chat_id: int, raw_code: str) -> bool:
    code = re.sub(r"[^A-Za-z0-9]", "", raw_code).upper()
    if len(code) != CODE_LEN:
        return False
    with db() as conn:
        with tx(conn):
            row = conn.execute("SELECT user_id, expires_at FROM telegram_link_codes WHERE code_hash = ?", (token_hash(code),)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM telegram_link_codes WHERE code_hash = ?", (token_hash(code),))  # single use
            if row["expires_at"] < now_iso():
                return False
            u = conn.execute("SELECT id, disabled FROM users WHERE id = ?", (row["user_id"],)).fetchone()
            if not u or u["disabled"]:
                return False
            conn.execute("DELETE FROM telegram_links WHERE user_id = ? OR chat_id = ?", (u["id"], chat_id))
            conn.execute("INSERT INTO telegram_links(chat_id, user_id) VALUES (?, ?)", (chat_id, u["id"]))
    return True


# ---------- message handling ----------

def _help_text(linked: bool) -> str:
    base = ("ARNET AI on Telegram.\n\n"
            "Just type a message and I will answer. Commands:\n"
            "/new  start a new conversation\n"
            "/tools  list tools, /tool NAME  switch tool\n"
            "/usage  messages used today\n"
            "/unlink  disconnect this chat\n\n"
            "I read text messages only. Photos, voice notes and files are not supported here yet.")
    if linked:
        return base
    return (base + "\n\nFirst connect your account: sign in to ARNET AI on the website, open Account, tap Connect Telegram, "
            "then send me /link followed by the code.")


def _need_link_text() -> str:
    return ("This chat is not connected to an ARNET AI account yet. Sign in on the website, open Account, tap Connect Telegram, "
            "then send me /link followed by the code. Send /help for details.")


def _user_from(row) -> dict:
    return {k: row[k] for k in ("id", "email", "name", "role", "plan", "created_at")}


def _handle(chat_id: int, text) -> None:
    if not isinstance(text, str) or not text.strip():
        send_plain(chat_id, "I can only read text messages for now.")
        return
    text = text.strip()
    rate_limit(f"tg:{chat_id}", 20, 60, "You are sending messages too quickly. Wait a few seconds.")
    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd, arg = cmd[1:].split("@")[0].lower(), arg.strip()
        if cmd in ("start", "help"):
            send_plain(chat_id, _help_text(linked=_get_link(chat_id) is not None))
            return
        if cmd == "link":
            rate_limit(f"tglink:{chat_id}", 6, 600, "Too many attempts. Wait a few minutes and try again.")
            if not arg:
                send_plain(chat_id, "Send /link followed by the code from the website, for example /link ABCD2345.")
            elif _redeem(chat_id, arg):
                send_plain(chat_id, "Connected. This chat now uses your ARNET AI account. Type a message to start. Send /help for commands.")
            else:
                send_plain(chat_id, "That code is not valid or has expired. On the website open Account, tap Connect Telegram to get a new one.")
            return
        row = _get_link(chat_id)
        if not row:
            send_plain(chat_id, _need_link_text())
            return
        if row["disabled"]:
            send_plain(chat_id, "Your ARNET AI account is not active.")
            return
        user = _user_from(row)
        if cmd == "new":
            _set_link(chat_id, conversation_id=None)
            send_plain(chat_id, "Started a new conversation.")
        elif cmd == "unlink":
            with db() as conn:
                conn.execute("DELETE FROM telegram_links WHERE chat_id = ?", (chat_id,))
            send_plain(chat_id, "Disconnected. Your conversations stay in your ARNET AI account.")
        elif cmd == "usage":
            with db() as conn:
                used = usage_today(conn, user["id"], "chat")
            lim = limits_for(user)["messages"]
            send_plain(chat_id, f"Plan: {user['plan']}. Messages today: {used}" + (f" of {lim}." if lim is not None else " (no limit)."))
        elif cmd == "tools":
            lines = [f"{t['id']}  {t['name']}" for t in TOOLS if availability(t)[0]]
            send_plain(chat_id, "Available tools (current: " + row["tool"] + "):\n" + "\n".join(lines) + "\n\nSwitch with /tool followed by the name, for example /tool writing.")
        elif cmd == "tool":
            t = BY_ID.get(arg.lower())
            if not t:
                send_plain(chat_id, "Unknown tool. Send /tools to see the list.")
            else:
                ok, why = availability(t)
                if not ok:
                    send_plain(chat_id, why)
                else:
                    _set_link(chat_id, conversation_id=None, tool=t["id"])
                    send_plain(chat_id, f"Switched to {t['name']}. This starts a new conversation.")
        else:
            send_plain(chat_id, "I do not know that command. Send /help.")
        return

    row = _get_link(chat_id)
    if not row:
        send_plain(chat_id, _need_link_text())
        return
    if row["disabled"]:
        send_plain(chat_id, "Your ARNET AI account is not active.")
        return
    _answer(chat_id, row, text)


def _set_link(chat_id: int, **fields) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)  # keys come from this file only, never from users
    with db() as conn:
        conn.execute(f"UPDATE telegram_links SET {sets} WHERE chat_id = ?", (*fields.values(), chat_id))


def _answer(chat_id: int, row, text: str) -> None:
    user = _user_from(row)
    body = {"message": text, "tool": row["tool"]}
    if row["conversation_id"]:
        body["conversation_id"] = row["conversation_id"]
    events = start_chat(user, body)  # raises ApiError for limits, unavailable provider, over-long messages
    parts: list[str] = []
    sources: list[dict] = []
    error, cid = "", None
    with _Typing(chat_id):
        try:
            for ev, data in events:
                if ev == "meta":
                    cid = data["conversation_id"]
                elif ev == "delta":
                    parts.append(data["text"])
                elif ev == "sources":
                    sources = data
                elif ev == "error":
                    error = data["message"]
        finally:
            events.close()
    if cid and cid != row["conversation_id"]:
        _set_link(chat_id, conversation_id=cid)
    if error and not parts:
        send_plain(chat_id, error)
        return
    answer = "".join(parts)
    if sources:
        answer += "\n\nSources:\n" + "\n".join(f"{i}. {s['title']} - {s['url']}" for i, s in enumerate(sources, 1))
    if error:
        answer += "\n\n(The reply was cut short: " + error + ")"
    send_answer(chat_id, answer)


# ---------- receiving updates ----------

_chat_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()
_slots = threading.BoundedSemaphore(8)  # at most 8 answers being written at once
_seen: "OrderedDict[int, None]" = OrderedDict()


def _first_time(update_id: int) -> bool:
    """Telegram resends an update if we answer slowly; process each update_id once."""
    with _locks_guard:
        if update_id in _seen:
            return False
        _seen[update_id] = None
        while len(_seen) > 2000:
            _seen.popitem(last=False)
        return True


def _lock_for(chat_id: int) -> threading.Lock:
    with _locks_guard:
        if len(_chat_locks) > 5000:
            _chat_locks.clear()
        return _chat_locks.setdefault(chat_id, threading.Lock())


def process_update(update) -> None:
    """Handle one Telegram update. Only private-chat text messages are used; groups and channels are ignored on purpose,
    because anyone in a group could otherwise spend a linked account's quota."""
    msg = update.get("message") if isinstance(update, dict) else None
    if not isinstance(msg, dict):
        return
    chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
    chat_id = chat.get("id")
    if chat.get("type") != "private" or not isinstance(chat_id, int):
        return
    if isinstance(msg.get("from"), dict) and msg["from"].get("is_bot"):
        return
    with _lock_for(chat_id), _slots:
        try:
            _handle(chat_id, msg.get("text"))
        except ApiError as e:
            send_plain(chat_id, e.message)
        except Exception as e:  # never show internals to the chat
            log_error("telegram", f"{type(e).__name__}: {str(e)[:150]}")
            send_plain(chat_id, "Something went wrong. Please try again in a moment.")


def dispatch(update) -> None:
    """Run an update in the background so the webhook can answer Telegram immediately."""
    uid = update.get("update_id") if isinstance(update, dict) else None
    if isinstance(uid, int) and not _first_time(uid):
        return
    threading.Thread(target=process_update, args=(update,), daemon=True).start()


def poll_forever(should_stop=lambda: False) -> None:
    """Long-polling loop for servers without a public HTTPS domain."""
    api("deleteWebhook", {"drop_pending_updates": False})
    register_commands()
    offset = None
    while not should_stop():
        params: dict = {"timeout": 25, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        try:
            updates = api("getUpdates", params, timeout=40) or []
        except TelegramError as e:
            log_error("telegram", f"polling failed: {e.description[:150]}")
            time.sleep(5)
            continue
        for u in updates:
            if isinstance(u, dict) and isinstance(u.get("update_id"), int):
                offset = u["update_id"] + 1
                dispatch(u)


# ---------- HTTP routes ----------

@route("/telegram/webhook", ["POST"], auth=None)
def webhook(ctx):
    e = env()
    if not (e.telegram_token and e.telegram_secret):
        raise ApiError(404, "Not found.")  # without a secret this endpoint would be open to anyone, so it stays off
    given = ctx.request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(given.encode(), e.telegram_secret.encode()):
        raise ApiError(403, "Forbidden.")
    dispatch(ctx.body)
    return {"ok": True}


@route("/api/me/telegram", ["GET"])
def telegram_status(ctx):
    if not configured():
        return {"configured": False, "linked": False}
    with db() as conn:
        row = conn.execute("SELECT linked_at FROM telegram_links WHERE user_id = ?", (ctx.user["id"],)).fetchone()
    return {"configured": True, "linked": bool(row), "linked_at": row["linked_at"] if row else None, "bot_username": bot_username()}


@route("/api/me/telegram/code", ["POST"])
def telegram_code(ctx):
    if not configured():
        raise ApiError(503, "The Telegram bot is not set up on this server yet.")
    rate_limit(f"tgcode:{ctx.user['id']}", 5, 3600, "Too many codes requested. Try again later.")
    return {"code": _make_code(ctx.user["id"]), "expires_in_minutes": CODE_MINUTES, "bot_username": bot_username()}


@route("/api/me/telegram", ["DELETE"])
def telegram_unlink(ctx):
    with db() as conn:
        conn.execute("DELETE FROM telegram_links WHERE user_id = ?", (ctx.user["id"],))
        conn.execute("DELETE FROM telegram_link_codes WHERE user_id = ?", (ctx.user["id"],))
    return {"ok": True}
