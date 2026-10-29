#!/bin/sh
# Fresh server + browser check. Needs Playwright with Chromium.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p /tmp/arnet-e2e
python3 tests/e2e/serve_fake.py > /tmp/arnet-e2e/server.log 2>&1 &
SERVER=$!
sleep 4
timeout 170 python3 tests/e2e/browser_check.py
code=$?
kill $SERVER 2>/dev/null
exit $code
