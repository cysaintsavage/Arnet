import base64
import http.cookiejar
import http.server
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request

import pytest

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()


class FakeUpstream(http.server.BaseHTTPRequestHandler):
    """Stands in for the AI, image and search vendors so the real HTTP/streaming code paths run in tests."""
    log: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        FakeUpstream.log.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path == "/v1/messages":
            if self.headers.get("x-api-key") != "test-key":
                self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"bad key"}'); return
            last = body["messages"][-1]["content"]
            if "TRIGGER_UPSTREAM_500" in last:
                self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"boom secret-detail"}'); return
            tag = (" [DOC]" if "<document>" in body["system"] else "") + (" [SEARCH]" if "<search_results>" in body["system"] else "")
            text = f"ECHO: {last}{tag}"
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for i in range(0, len(text), 5):
                ev = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text[i:i + 5]}}
                self.wfile.write(f"event: content_block_delta\ndata: {json.dumps(ev)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b'event: message_stop\ndata: {"type":"message_stop"}\n\n')
        elif self.path == "/images/generations":
            out = json.dumps({"data": [{"b64_json": PNG}]}).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(out)
        elif self.path == "/search":
            out = json.dumps({"results": [{"title": "Example", "url": "https://example.com/a", "content": "Example snippet"},
                                          {"title": "Bad", "url": "javascript:alert(1)", "content": "x"}]}).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(out)
        else:
            self.send_response(404); self.end_headers()


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="session")
def server():
    tmp = tempfile.mkdtemp(prefix="arnet-test-")
    up_port, app_port = _free_port(), _free_port()
    up = http.server.ThreadingHTTPServer(("127.0.0.1", up_port), FakeUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    os.environ.update({
        "DATA_DIR": tmp, "DATABASE_PATH": os.path.join(tmp, "t.sqlite3"),
        "AI_PROVIDER": "anthropic", "AI_API_KEY": "test-key", "AI_BASE_URL": f"http://127.0.0.1:{up_port}",
        "IMAGE_API_KEY": "img-key", "IMAGE_BASE_URL": f"http://127.0.0.1:{up_port}",
        "SEARCH_API_KEY": "s-key", "SEARCH_BASE_URL": f"http://127.0.0.1:{up_port}",
        "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
    })
    for k in ("SMTP_HOST", "SMTP_FROM"):
        os.environ.pop(k, None)
    import uvicorn
    from app.main import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=app_port, log_level="warning")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{app_port}"
    srv.should_exit = True
    up.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method, path, data=None, raw=None, headers=None, csrf=True):
        h = {"X-Requested-With": "arnet-web"} if csrf else {}
        h.update(headers or {})
        body = None
        if raw is not None:
            body = raw
        elif data is not None:
            body = json.dumps(data).encode(); h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=h)
        try:
            r = self.opener.open(req, timeout=30)
        except urllib.error.HTTPError as e:
            r = e
        payload = r.read()
        ct = r.headers.get("content-type", "")
        parsed = json.loads(payload) if "json" in ct and payload else payload
        return r.status, parsed, r.headers

    def get(self, p, **k): return self.call("GET", p, **k)
    def post(self, p, d=None, **k): return self.call("POST", p, data=d if d is not None else {}, **k)
    def patch(self, p, d, **k): return self.call("PATCH", p, data=d, **k)
    def put(self, p, d, **k): return self.call("PUT", p, data=d, **k)
    def delete(self, p, d=None, **k): return self.call("DELETE", p, data=d, **k)

    def stream(self, d):
        """POST /api/chat and parse the SSE stream into [(event, data)]."""
        s, body, h = self.call("POST", "/api/chat", data=d)
        if s != 200:
            return s, body
        events = []
        for block in body.decode().split("\n\n"):
            if not block.strip():
                continue
            ev = block.split("\n")[0][7:]
            data = json.loads(block.split("\n")[1][6:])
            events.append((ev, data))
        return s, events


_n = [0]


@pytest.fixture
def make_user(server):
    from app.security import limiter
    def make(email=None, password="correct horse battery"):
        limiter.reset()
        _n[0] += 1
        c = Client(server)
        email = email or f"user{_n[0]}@example.com"
        s, b, _ = c.post("/api/auth/register", {"email": email, "password": password, "name": "T"})
        assert s == 200, b
        c.email, c.password, c.id = email, password, b["user"]["id"]
        return c
    return make


@pytest.fixture
def admin(server, make_user):
    from app.db import db
    c = make_user(email=f"admin{_n[0]+1}@example.com")
    with db() as conn:
        conn.execute("UPDATE users SET role='admin' WHERE id=?", (c.id,))
    return c


@pytest.fixture(autouse=True)
def _reset_state(server):
    from app.security import limiter
    limiter.reset()
    FakeUpstream.log.clear()
    yield
