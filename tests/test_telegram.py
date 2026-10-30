"""Telegram bot tests: real webhook route, real chat engine, fake Telegram and fake AI vendor."""
import itertools
import threading
import time

import pytest

from tests.conftest import Client, FakeTelegram, FakeUpstream

SECRET = "test-webhook-secret-0123456789"
_uid = itertools.count(1000)
_chat = itertools.count(5000)


def send(server, chat_id, text, chat_type="private", secret=SECRET, is_bot=False):
    """Deliver a Telegram update to the webhook exactly as Telegram would."""
    c = Client(server)
    update = {"update_id": next(_uid), "message": {"message_id": 1, "chat": {"id": chat_id, "type": chat_type},
                                                    "from": {"id": chat_id, "is_bot": is_bot}, "date": 0}}
    if text is not None:
        update["message"]["text"] = text
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret is not None else {}
    return c.call("POST", "/telegram/webhook", data=update, headers=headers, csrf=False)


def wait_sent(chat_id, count=1, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        got = FakeTelegram.sent(chat_id)
        if len(got) >= count:
            return got
        time.sleep(0.05)
    raise AssertionError(f"expected {count} message(s) to chat {chat_id}, got {FakeTelegram.sent(chat_id)}")


def say(server, chat_id, text, count=None):
    """Send a message and return the bot's next reply text."""
    before = len(FakeTelegram.sent(chat_id))
    s, _, _ = send(server, chat_id, text)
    assert s == 200
    return wait_sent(chat_id, before + 1)[before]["text"]


def link(server, user, chat_id):
    s, b, _ = user.post("/api/me/telegram/code")
    assert s == 200, b
    return say(server, chat_id, f"/link {b['code']}"), b["code"]


# ---------- webhook security ----------

def test_webhook_requires_the_secret(server):
    assert send(server, 1, "hi", secret=None)[0] == 403
    assert send(server, 1, "hi", secret="wrong")[0] == 403
    assert send(server, 1, "hi")[0] == 200


def test_webhook_off_without_secret(server, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    assert send(server, 1, "hi", secret="")[0] == 404


def test_duplicate_updates_are_processed_once(server):
    chat = next(_chat)
    c = Client(server)
    upd = {"update_id": 777001, "message": {"chat": {"id": chat, "type": "private"}, "from": {"id": chat}, "text": "/help"}}
    h = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    assert c.call("POST", "/telegram/webhook", data=upd, headers=h, csrf=False)[0] == 200
    wait_sent(chat, 1)
    assert c.call("POST", "/telegram/webhook", data=upd, headers=h, csrf=False)[0] == 200
    time.sleep(0.5)
    assert len(FakeTelegram.sent(chat)) == 1


# ---------- linking ----------

def test_unlinked_chat_cannot_use_the_ai(server):
    chat = next(_chat)
    reply = say(server, chat, "hello there")
    assert "not connected" in reply and "Connect Telegram" in reply
    assert FakeUpstream.log == []


def test_link_chat_and_save_history(server, make_user):
    u = make_user()
    chat = next(_chat)
    s, b, _ = u.get("/api/me/telegram")
    assert b["configured"] is True and b["linked"] is False and b["bot_username"] == "arnet_test_bot"
    reply, _ = link(server, u, chat)
    assert "Connected" in reply
    assert u.get("/api/me/telegram")[1]["linked"] is True
    answer = say(server, chat, "hello from telegram")
    assert "ECHO: hello from telegram" in answer
    convs = u.get("/api/conversations")[1]["conversations"]
    assert len(convs) == 1
    msgs = u.get(f"/api/conversations/{convs[0]['id']}")[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert u.get("/api/me/usage")[1]["messages_today"] == 1
    # a second message continues the same conversation
    say(server, chat, "second")
    assert len(u.get("/api/conversations")[1]["conversations"]) == 1
    assert len(u.get(f"/api/conversations/{convs[0]['id']}")[1]["messages"]) == 4


def test_codes_are_single_use_and_wrong_codes_fail(server, make_user):
    a, b = make_user(), make_user()
    chat_a, chat_b = next(_chat), next(_chat)
    reply, code = link(server, a, chat_a)
    assert "Connected" in reply
    assert "not valid" in say(server, chat_b, f"/link {code}")
    assert "not valid" in say(server, chat_b, "/link ZZZZ9999")
    assert "not valid" in say(server, chat_b, "/link abc")
    assert "not connected" in say(server, chat_b, "hi")


def test_link_attempts_are_rate_limited(server):
    chat = next(_chat)
    for _ in range(6):
        assert "not valid" in say(server, chat, "/link AAAAAAAA")
    assert "Too many attempts" in say(server, chat, "/link AAAAAAAA")


def test_relinking_moves_the_account_to_the_new_chat(server, make_user):
    u = make_user()
    old, new = next(_chat), next(_chat)
    link(server, u, old)
    link(server, u, new)
    assert "not connected" in say(server, old, "still there?")
    assert "ECHO" in say(server, new, "yes")


def test_two_accounts_stay_separate(server, make_user):
    a, b = make_user(), make_user()
    ca, cb = next(_chat), next(_chat)
    link(server, a, ca); link(server, b, cb)
    say(server, ca, "secret of A")
    say(server, cb, "secret of B")
    ta = [c["title"] for c in a.get("/api/conversations")[1]["conversations"]]
    tb = [c["title"] for c in b.get("/api/conversations")[1]["conversations"]]
    assert ta == ["secret of A"] and tb == ["secret of B"]
    assert a.get("/api/me/usage")[1]["messages_today"] == 1


def test_website_unlink_and_account_deletion(server, make_user):
    from app.db import db
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    assert u.delete("/api/me/telegram")[0] == 200
    assert "not connected" in say(server, chat, "hi")
    chat2 = next(_chat)
    link(server, u, chat2)
    assert u.delete("/api/me", {"password": u.password})[0] == 200
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM telegram_links WHERE chat_id = ?", (chat2,)).fetchone()["c"] == 0


def test_disabled_account_is_refused(server, make_user, admin):
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    assert admin.patch(f"/api/admin/users/{u.id}", {"disabled": True})[0] == 200
    assert "not active" in say(server, chat, "hello")
    assert admin.patch(f"/api/admin/users/{u.id}", {"disabled": False})[0] == 200


def test_code_endpoint_needs_login(server):
    assert Client(server).post("/api/me/telegram/code")[0] == 401


# ---------- commands ----------

def test_commands(server, make_user):
    u = make_user()
    chat = next(_chat)
    assert "/link" in say(server, chat, "/start")
    link(server, u, chat)
    say(server, chat, "one")
    assert "Messages today: 1 of" in say(server, chat, "/usage")
    assert "writing" in say(server, chat, "/tools")
    assert "Unknown tool" in say(server, chat, "/tool nonsense")
    assert "Writing Assistant" in say(server, chat, "/tool writing")
    FakeUpstream.log.clear()
    say(server, chat, "draft an email")
    assert any("skilled editor" in body.get("system", "") for _, _, body in FakeUpstream.log)
    assert "new conversation" in say(server, chat, "/new").lower()
    assert len(u.get("/api/conversations")[1]["conversations"]) == 2
    assert "do not know" in say(server, chat, "/nope")
    assert "Disconnected" in say(server, chat, "/unlink")
    assert "not connected" in say(server, chat, "hi")


def test_command_with_bot_name_suffix(server):
    assert "ARNET AI on Telegram" in say(server, next(_chat), "/help@arnet_test_bot")


# ---------- what the bot ignores or refuses ----------

def test_groups_bots_and_non_text_are_ignored_or_politely_refused(server, make_user):
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    before = len(FakeTelegram.log)
    assert send(server, -100999, "hello", chat_type="supergroup")[0] == 200
    assert send(server, chat, "hello", is_bot=True)[0] == 200
    time.sleep(0.6)
    assert [m for m, _ in FakeTelegram.log[before:] if m == "sendMessage"] == []
    assert "only read text" in say_none(server, chat)
    assert u.get("/api/me/usage")[1]["messages_today"] == 0


def say_none(server, chat_id):
    before = len(FakeTelegram.sent(chat_id))
    assert send(server, chat_id, None)[0] == 200
    return wait_sent(chat_id, before + 1)[before]["text"]


def test_daily_limit_applies_in_telegram(server, make_user, admin):
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    assert admin.put("/api/admin/settings", {"free_daily_messages": 1})[0] == 200
    try:
        assert "ECHO" in say(server, chat, "first")
        assert "used all 1 messages" in say(server, chat, "second")
    finally:
        admin.put("/api/admin/settings", {"free_daily_messages": 20})


def test_provider_failure_does_not_leak_details(server, make_user):
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    reply = say(server, chat, "TRIGGER_UPSTREAM_500")
    assert "secret-detail" not in reply and "123:testtoken" not in reply
    assert "error" in reply.lower() or "try again" in reply.lower()


def test_over_long_message_is_refused_politely(server, make_user):
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    assert "too long" in say(server, chat, "x" * 9000)


# ---------- formatting ----------

def test_formatting_escapes_everything_and_keeps_code():
    from app.telegram import to_html
    out = to_html("**Hi** <script>alert(1)</script> & `x < y`\n```python\nprint('<b>')\n```\n[ok](https://e.com/a?b=1&c=2) [bad](javascript:alert(1))")
    assert "<b>Hi</b>" in out
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<code>x &lt; y</code>" in out
    assert '<pre><code class="language-python">print(\'&lt;b&gt;\')</code></pre>' in out
    assert '<a href="https://e.com/a?b=1&amp;c=2">ok</a>' in out
    assert "<a href=\"javascript" not in out


def test_long_answers_are_split_and_code_blocks_stay_closed():
    from app.telegram import split_message
    text = "intro\n```python\n" + "\n".join(f"line {i} " + "x" * 50 for i in range(200)) + "\n```\noutro"
    pieces = split_message(text)
    assert len(pieces) > 1 and all(len(p) <= 3500 for p in pieces)
    for p in pieces:
        assert p.count("```") % 2 == 0, "every piece must open and close its own code block"
    assert "outro" in pieces[-1]
    assert split_message("a" * 9000)[0] and all(len(p) <= 3500 for p in split_message("a" * 9000))


def test_formatting_rejected_by_telegram_falls_back_to_plain_text(server, make_user):
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    before = len(FakeTelegram.sent(chat))
    send(server, chat, "FORCE_PARSE_ERROR")
    got = wait_sent(chat, before + 2)
    assert got[before].get("parse_mode") == "HTML"
    assert "parse_mode" not in got[before + 1] and "ECHO: FORCE_PARSE_ERROR" in got[before + 1]["text"]


def test_web_research_sources_are_listed(server, make_user):
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    say(server, chat, "/tool research")
    reply = say(server, chat, "latest news")
    assert "Sources:" in reply and "https://example.com/a" in reply and "javascript:" not in reply


# ---------- admin and command line ----------

def test_admin_health_lists_telegram(server, admin):
    items = {i["name"]: i for i in admin.get("/api/admin/health")[1]["services"]}
    assert items["Telegram bot"]["status"] == "ok"
    assert "123:testtoken" not in str(items)


def test_cli_info_and_webhook(server, monkeypatch, capsys):
    from app.cli import main
    assert main(["telegram-info"]) == 0
    assert "@arnet_test_bot" in capsys.readouterr().out
    assert main(["telegram-webhook"]) == 1  # test APP_BASE_URL is http://, Telegram needs https
    assert "https" in capsys.readouterr().out
    monkeypatch.setenv("APP_BASE_URL", "https://arnet.example")
    FakeTelegram.log.clear()
    assert main(["telegram-webhook"]) == 0
    calls = dict(FakeTelegram.log)
    assert calls["setWebhook"]["url"] == "https://arnet.example/telegram/webhook"
    assert calls["setWebhook"]["secret_token"] == SECRET
    assert "setMyCommands" in calls
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "short")
    assert main(["telegram-webhook"]) == 1


def test_cli_without_token(monkeypatch, capsys):
    from app.cli import main
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    assert main(["telegram-info"]) == 1
    assert "BotFather" in capsys.readouterr().out


def test_polling_mode_answers_messages(server, make_user):
    from app import telegram
    u = make_user()
    chat = next(_chat)
    link(server, u, chat)
    stop = threading.Event()
    t = threading.Thread(target=telegram.poll_forever, args=(stop.is_set,), daemon=True)
    FakeTelegram.updates.append({"update_id": next(_uid), "message": {"chat": {"id": chat, "type": "private"}, "from": {"id": chat}, "text": "hello by polling"}})
    before = len(FakeTelegram.sent(chat))
    t.start()
    try:
        got = wait_sent(chat, before + 1)
        assert "ECHO: hello by polling" in got[before]["text"]
        assert any(m == "deleteWebhook" for m, _ in FakeTelegram.log)
    finally:
        stop.set()
        t.join(timeout=5)
