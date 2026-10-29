import io
import json
import zipfile

from tests.conftest import Client, FakeUpstream


# ---------- auth ----------

def test_register_login_logout_me(server, make_user):
    c = make_user()
    s, b, h = c.get("/api/me")
    assert s == 200 and b["user"]["email"] == c.email and b["user"]["role"] == "user"
    cookie = [x for x in h.get_all("set-cookie") or []]
    s, b, _ = c.post("/api/auth/logout")
    assert s == 200
    assert c.get("/api/me")[0] == 401
    s, b, h = c.post("/api/auth/login", {"email": c.email.upper(), "password": c.password})
    assert s == 200
    sc = h.get("set-cookie")
    assert "HttpOnly" in sc and "SameSite=lax" in sc
    assert c.get("/api/me")[0] == 200


def test_bad_credentials_and_validation(server, make_user):
    c = make_user()
    anon = Client(server)
    assert anon.post("/api/auth/login", {"email": c.email, "password": "wrong password"})[0] == 401
    assert anon.post("/api/auth/login", {"email": "nobody@example.com", "password": "wrong password"})[0] == 401
    assert anon.post("/api/auth/register", {"email": "bad", "password": "longenough1"})[0] == 400
    assert anon.post("/api/auth/register", {"email": "a@example.com", "password": "short"})[0] == 400
    assert anon.post("/api/auth/register", {"email": c.email, "password": "longenough1"})[0] == 409


def test_login_rate_limit(server, make_user):
    c = make_user()
    anon = Client(server)
    codes = [anon.post("/api/auth/login", {"email": c.email, "password": "nope nope"})[0] for _ in range(10)]
    assert codes[:8] == [401] * 8 and 429 in codes[8:]


def test_csrf_protection(server, make_user):
    c = make_user()
    assert c.post("/api/auth/logout", csrf=False)[0] == 403
    s, _, _ = c.post("/api/conversations", headers={"Origin": "https://evil.example"})
    assert s in (403, 405)
    s, _, _ = c.call("PATCH", "/api/me", data={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert s == 403
    assert c.get("/api/me")[0] == 200  # GET unaffected


def test_security_headers(server):
    s, _, h = Client(server).get("/")
    assert s == 200
    assert "default-src 'self'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"


def test_password_change_revokes_other_sessions(server, make_user):
    a = make_user()
    b = Client(server)
    assert b.post("/api/auth/login", {"email": a.email, "password": a.password})[0] == 200
    assert a.post("/api/me/password", {"current": "wrong", "new": "brand new password"})[0] == 400
    assert a.post("/api/me/password", {"current": a.password, "new": "brand new password"})[0] == 200
    assert a.get("/api/me")[0] == 200
    assert b.get("/api/me")[0] == 401


def test_forgot_password_requires_email_setup_then_works(server, make_user, monkeypatch):
    c = make_user()
    anon = Client(server)
    s, b, _ = anon.post("/api/auth/forgot", {"email": c.email})
    assert s == 503 and "not set up" in b["error"]
    from app import mailer
    sent = []
    monkeypatch.setenv("SMTP_HOST", "smtp.invalid"); monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    monkeypatch.setattr(mailer, "send", lambda to, subj, body: sent.append((to, body)))
    s, b, _ = anon.post("/api/auth/forgot", {"email": c.email})
    assert s == 200 and len(sent) == 1
    s2, b2, _ = anon.post("/api/auth/forgot", {"email": "ghost@example.com"})
    assert s2 == 200 and b2 == b and len(sent) == 1  # same answer whether or not the account exists
    token = sent[0][1].split("token=")[1].split()[0]
    assert anon.post("/api/auth/reset", {"token": token, "password": "a fresh password"})[0] == 200
    assert anon.post("/api/auth/reset", {"token": token, "password": "another one here"})[0] == 400  # single use
    assert c.get("/api/me")[0] == 401  # old sessions revoked
    assert anon.post("/api/auth/login", {"email": c.email, "password": "a fresh password"})[0] == 200


def test_delete_account_removes_data(server, make_user):
    c = make_user()
    c.stream({"message": "hello"})
    s, b, _ = c.delete("/api/me", {"password": "wrong"})
    assert s == 400
    assert c.delete("/api/me", {"password": c.password})[0] == 200
    assert c.get("/api/me")[0] == 401
    from app.db import db
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversations WHERE user_id=?", (c.id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM users WHERE id=?", (c.id,)).fetchone()[0] == 0


# ---------- authorization ----------

def test_registering_with_owner_email_does_not_grant_admin(server):
    anon = Client(server)
    s, b, _ = anon.post("/api/auth/register", {"email": "realchrris@gmail.com", "password": "correct horse battery"})
    assert s == 200 and b["user"]["role"] == "user"
    assert anon.get("/api/admin/stats")[0] == 403


def test_admin_endpoints_need_server_side_admin(server, make_user, admin):
    anon, user = Client(server), make_user()
    for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/settings", "/api/admin/health", "/api/admin/errors", "/api/admin/requests"):
        assert anon.get(path)[0] == 401
        assert user.get(path)[0] == 403
        assert admin.get(path)[0] == 200
    assert user.patch(f"/api/admin/users/{user.id}", {"role": "admin"})[0] == 403
    assert user.put("/api/admin/settings", {"free_daily_messages": 999})[0] == 403


def test_demoted_or_disabled_admin_loses_access_immediately(server, admin, make_user):
    other = make_user()
    from app.db import db
    with db() as conn:
        conn.execute("UPDATE users SET role='admin' WHERE id=?", (other.id,))
    assert other.get("/api/admin/stats")[0] == 200
    assert admin.patch(f"/api/admin/users/{other.id}", {"role": "user"})[0] == 200
    assert other.get("/api/admin/stats")[0] == 401 or other.get("/api/admin/stats")[0] == 403
    assert admin.patch(f"/api/admin/users/{other.id}", {"disabled": True})[0] == 200
    assert other.get("/api/me")[0] == 401
    assert Client(server).post("/api/auth/login", {"email": other.email, "password": other.password})[0] == 401


def test_admin_cannot_lock_themselves_out(admin):
    assert admin.patch(f"/api/admin/users/{admin.id}", {"role": "user"})[0] == 400
    assert admin.patch(f"/api/admin/users/{admin.id}", {"disabled": True})[0] == 400
    assert admin.patch(f"/api/admin/users/{admin.id}", {"plan": "pro"})[0] == 200


def test_users_cannot_see_each_others_data(server, make_user):
    a, b = make_user(), make_user()
    ev = a.stream({"message": "secret plan alpha"})[1]
    cid = ev[0][1]["conversation_id"]
    assert b.get(f"/api/conversations/{cid}")[0] == 404
    assert b.patch(f"/api/conversations/{cid}", {"title": "hijack"})[0] == 404
    assert b.delete(f"/api/conversations/{cid}")[0] == 404
    assert b.stream({"message": "hi", "conversation_id": cid})[0] == 404
    assert b.get("/api/conversations?q=alpha")[1]["conversations"] == []
    assert a.get("/api/conversations?q=alpha")[1]["conversations"][0]["id"] == cid
    s, d, _ = a.call("POST", "/api/documents", raw=b"private notes", headers={"X-Filename": "n.txt"})
    did = d["document"]["id"]
    assert b.delete(f"/api/documents/{did}")[0] == 404
    assert b.stream({"message": "x", "document_id": did})[0] == 404
    assert b.get("/api/documents")[1]["documents"] == []
    iid = a.post("/api/images", {"prompt": "a cat"})[1]["image"]["id"]
    assert b.get(f"/api/images/{iid}/file")[0] == 404
    assert a.get(f"/api/images/{iid}/file")[0] == 200


# ---------- chat ----------

def test_chat_streams_and_persists(server, make_user):
    c = make_user()
    s, ev = c.stream({"message": "hello world"})
    kinds = [e for e, _ in ev]
    assert s == 200 and kinds[0] == "meta" and kinds[-1] == "done" and kinds.count("delta") > 1
    text = "".join(d["text"] for e, d in ev if e == "delta")
    assert text == "ECHO: hello world"
    cid = ev[0][1]["conversation_id"]
    s, b, _ = c.get(f"/api/conversations/{cid}")
    assert [m["role"] for m in b["messages"]] == ["user", "assistant"] and b["messages"][1]["content"] == text
    # the API key is sent upstream but never to the browser
    assert FakeUpstream.log[0][1].get("x-api-key") == "test-key"
    # follow-up includes history
    c.stream({"message": "again", "conversation_id": cid})
    assert [m["content"] for m in FakeUpstream.log[-1][2]["messages"]] == ["hello world", "ECHO: hello world", "again"]


def test_conversation_rename_search_delete_regenerate(server, make_user):
    c = make_user()
    cid = c.stream({"message": "findme-token please"})[1][0][1]["conversation_id"]
    assert c.patch(f"/api/conversations/{cid}", {"title": "My title"})[1]["title"] == "My title"
    assert [x["id"] for x in c.get("/api/conversations?q=findme-token")[1]["conversations"]] == [cid]
    assert [x["id"] for x in c.get("/api/conversations?q=My%20ti")[1]["conversations"]] == [cid]
    assert c.get("/api/conversations?q=%25")[1]["conversations"] == []  # wildcard characters are escaped
    s, ev = c.stream({"conversation_id": cid, "regenerate": True})
    assert s == 200 and ev[-1][0] == "done"
    msgs = c.get(f"/api/conversations/{cid}")[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert c.delete(f"/api/conversations/{cid}")[0] == 200
    assert c.get(f"/api/conversations/{cid}")[0] == 404


def test_tools_use_their_own_system_prompt(server, make_user):
    c = make_user()
    c.stream({"message": "fix this", "tool": "code-debug"})
    assert "debugger" in FakeUpstream.log[-1][2]["system"]
    assert c.stream({"message": "x", "tool": "nope"})[0] == 400


def test_upstream_failure_is_reported_without_leaking_details(server, make_user, admin):
    c = make_user()
    s, ev = c.stream({"message": "TRIGGER_UPSTREAM_500"})
    assert s == 200 and ev[-1][0] == "error"
    assert "secret-detail" not in json.dumps(ev)
    errs = admin.get("/api/admin/errors")[1]["errors"]
    assert any("secret-detail" in e["message"] for e in errs)  # visible to the owner only
    cid = ev[0][1]["conversation_id"]
    assert [m["role"] for m in c.get(f"/api/conversations/{cid}")[1]["messages"]] == ["user"]


def test_chat_not_configured(server, make_user, monkeypatch):
    c = make_user()
    monkeypatch.setenv("AI_API_KEY", "")
    s, b, _ = c.post("/api/chat", {"message": "hi"})
    assert s == 503 and "AI_API_KEY" in b["error"]
    assert not next(t for t in c.get("/api/tools")[1]["tools"] if t["id"] == "chat")["available"]


def test_daily_limits_enforced_and_configurable(server, make_user, admin):
    c = make_user()
    assert admin.put("/api/admin/settings", {"free_daily_messages": 2})[0] == 200
    assert c.stream({"message": "1"})[0] == 200
    assert c.stream({"message": "2"})[0] == 200
    s, b = c.stream({"message": "3"})
    assert s == 402 and "2 messages" in b["error"]
    u = c.get("/api/me/usage")[1]
    assert u["messages_today"] == 2 and u["messages_limit"] == 2
    assert admin.patch(f"/api/admin/users/{c.id}", {"plan": "pro"})[0] == 200
    assert c.stream({"message": "4"})[0] == 200
    assert admin.put("/api/admin/settings", {"free_daily_messages": 20})[0] == 200


def test_message_validation(server, make_user):
    c = make_user()
    assert c.post("/api/chat", {"message": "   "})[0] == 400
    assert c.post("/api/chat", {"message": "x" * 9000})[0] == 400
    assert c.post("/api/chat", {"message": 5})[0] == 400


# ---------- documents ----------

def _docx(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>")
    return buf.getvalue()


def test_document_upload_validation_and_analysis(server, make_user):
    c = make_user()
    up = lambda name, raw: c.call("POST", "/api/documents", raw=raw, headers={"X-Filename": name})
    assert up("a.exe", b"MZ....")[0] == 400
    assert up("fake.pdf", b"not a pdf")[0] == 400
    assert up("bin.txt", b"abc\x00def")[0] == 400
    assert up("empty.txt", b"")[0] == 400
    assert up("../../etc/passwd.txt", b"hello")[1]["document"]["filename"] == "passwd.txt"
    s, d, _ = up("memo.docx", _docx("Quarterly revenue grew 12 percent"))
    assert s == 200 and d["document"]["chars"] > 10
    did = d["document"]["id"]
    ev = c.stream({"message": "summarize", "document_id": did, "tool": "summarize"})[1]
    assert "[DOC]" in "".join(x["text"] for e, x in ev if e == "delta")
    assert "Quarterly revenue grew 12 percent" in FakeUpstream.log[-1][2]["system"]
    assert c.delete(f"/api/documents/{did}")[0] == 200
    big = b"a" * (5 * 1024 * 1024 + 1)
    assert up("big.txt", big)[0] == 413


def test_pdf_text_extraction(server, make_user):
    from pypdf import PdfWriter
    c = make_user()
    w = PdfWriter(); w.add_blank_page(200, 200)
    buf = io.BytesIO(); w.write(buf)
    s, b, _ = c.call("POST", "/api/documents", raw=buf.getvalue(), headers={"X-Filename": "blank.pdf"})
    assert s == 400 and "No readable text" in b["error"]  # valid PDF, no text layer: clear message, no crash


# ---------- research, images, previews ----------

def test_web_research_returns_sources_separately(server, make_user):
    c = make_user()
    s, ev = c.stream({"message": "what is example?", "tool": "research"})
    kinds = [e for e, _ in ev]
    assert "sources" in kinds and kinds.index("sources") < kinds.index("delta")
    src = next(d for e, d in ev if e == "sources")
    assert src == [{"title": "Example", "url": "https://example.com/a", "snippet": "Example snippet"}]  # javascript: URL dropped
    assert "From sources" in FakeUpstream.log[-1][2]["system"] and "My analysis" in FakeUpstream.log[-1][2]["system"]
    cid = ev[0][1]["conversation_id"]
    assert c.get(f"/api/conversations/{cid}")[1]["messages"][-1]["sources"][0]["url"] == "https://example.com/a"


def test_research_unavailable_without_search_key(server, make_user, monkeypatch):
    c = make_user()
    monkeypatch.setenv("SEARCH_API_KEY", "")
    s, b, _ = c.post("/api/chat", {"message": "x", "tool": "research"})
    assert s == 503 and "SEARCH_API_KEY" in b["error"]


def test_image_generation_and_limits(server, make_user, admin, monkeypatch):
    c = make_user()
    s, b, _ = c.post("/api/images", {"prompt": "a lighthouse"})
    assert s == 200
    s, raw, h = c.get(f"/api/images/{b['image']['id']}/file")
    assert s == 200 and h["content-type"] == "image/png" and raw.startswith(b"\x89PNG")
    assert admin.put("/api/admin/settings", {"free_daily_images": 1})[0] == 200
    assert c.post("/api/images", {"prompt": "again"})[0] == 402
    assert admin.put("/api/admin/settings", {"free_daily_images": 3})[0] == 200
    monkeypatch.setenv("IMAGE_API_KEY", "")
    assert c.post("/api/images", {"prompt": "x"})[0] == 503


def test_preview_is_sandboxed_and_private(server, make_user):
    a, b = make_user(), make_user()
    s, d, _ = a.post("/api/previews", {"html": "<h1>hi</h1><script>1</script>"})
    s, body, h = a.get(d["url"])
    assert s == 200 and b"<h1>hi</h1>" in body
    csp = h["content-security-policy"]
    assert csp.startswith("sandbox allow-scripts") and "allow-same-origin" not in csp and "connect-src 'none'" in csp
    assert b.get(d["url"])[0] == 404
    assert Client(server).get(d["url"])[0] == 401


# ---------- admin ----------

def test_admin_settings_validation_and_public_contact(server, admin):
    s, b, _ = Client(server).get("/api/public/config")
    assert b["contact_email"] == "realchrris@gmail.com" and b["whatsapp"] == "0746940886"
    assert b["whatsapp_link"] == "https://wa.me/254746940886" and b["creator"] == "Chris (ZYNTHEX)"
    assert b["payments_active"] is False
    assert admin.put("/api/admin/settings", {"unknown": "x"})[0] == 400
    assert admin.put("/api/admin/settings", {"free_daily_messages": "abc"})[0] == 400
    assert admin.put("/api/admin/settings", {"contact_email": "nope"})[0] == 400
    assert admin.put("/api/admin/settings", {"ai_provider": "evil"})[0] == 400
    assert admin.put("/api/admin/settings", {"registration_open": "yes"})[0] == 400


def test_admin_dashboard_data(server, admin, make_user):
    u = make_user()
    u.stream({"message": "count me"})
    st = admin.get("/api/admin/stats")[1]
    assert st["users_total"] >= 2 and st["messages"] >= 2 and st["requests_24h"] >= 1
    users = admin.get("/api/admin/users?q=" + u.email.split("@")[0])[1]["users"]
    assert [x["email"] for x in users] == [u.email]
    assert "password_hash" not in json.dumps(users)
    reqs = admin.get("/api/admin/requests")[1]["requests"]
    assert reqs[0]["kind"] in ("chat", "image") and "email" in reqs[0]
    health = {x["name"]: x for x in admin.get("/api/admin/health")[1]["services"]}
    assert health["Payments"]["status"] == "not_implemented" and health["Database"]["status"] == "ok"


def test_closing_registration(server, admin):
    anon = Client(server)
    assert admin.put("/api/admin/settings", {"registration_open": False})[0] == 200
    assert anon.post("/api/auth/register", {"email": "late@example.com", "password": "correct horse battery"})[0] == 403
    assert admin.put("/api/admin/settings", {"registration_open": True})[0] == 200


def test_api_unknown_route_is_json_and_health(server):
    c = Client(server)
    s, b, _ = c.get("/api/nope")
    assert s == 404 and b == {"error": "Not found."}
    assert c.get("/api/health")[1] == {"status": "ok"}
    assert c.get("/api/tools")[1]["tools"][0]["id"] == "chat"


def test_cli_migrate_idempotent_and_promote(server, make_user):
    from app import cli
    from app.db import db
    assert cli.main(["migrate"]) == 0
    u = make_user()
    assert cli.main(["promote", u.email]) == 0
    assert u.get("/api/admin/stats")[0] == 200
    assert cli.main(["promote", "ghost@example.com"]) == 1
