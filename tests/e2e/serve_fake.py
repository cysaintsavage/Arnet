"""Run the real app against the fake AI/image/search vendor from the tests, for browser testing only."""
import http.server, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tests.conftest import FakeUpstream
import shutil
tmp = "/tmp/arnet-e2e/data"; shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
up = http.server.ThreadingHTTPServer(("127.0.0.1", 9911), FakeUpstream)
threading.Thread(target=up.serve_forever, daemon=True).start()
os.environ.update({"DATA_DIR": tmp, "AI_API_KEY": "test-key", "AI_BASE_URL": "http://127.0.0.1:9911", "IMAGE_API_KEY": "i", "IMAGE_BASE_URL": "http://127.0.0.1:9911",
                   "SEARCH_API_KEY": "s", "SEARCH_BASE_URL": "http://127.0.0.1:9911", "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
import uvicorn
from app.main import app
from app.db import db
from app.security import hash_password
with db() as c:
    c.execute("INSERT INTO users(email,password_hash,name,role,plan) VALUES ('owner@example.com',?, 'Chris','admin','pro')", (hash_password('owner password 123'),))
uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
