# ARNET AI

*One Intelligence. Infinite Possibilities.*
Owner: Chris. Built by Chris (ZYNTHEX). Contact: realchrris@gmail.com, WhatsApp 0746940886.

A self-hosted AI platform: chat with history, a coding assistant, a website builder with live preview, document analysis, web research, image generation, a tools directory, user accounts, and an owner dashboard. You supply the AI provider key. Nothing in the app is simulated: a feature that needs a key you have not set shows "Needs setup" and says what is missing.

## Quick start (local)

Built and tested on Python 3.13. It should run on 3.10 or newer, but older versions were not tried.

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then edit .env and set AI_API_KEY
set -a; . ./.env; set +a        # the app reads real environment variables; it does not parse .env itself
python -m app.cli migrate
python -m app.cli create-admin you@example.com   # asks for a password
uvicorn app.main:app --port 8000
```

Open http://localhost:8000, sign in with the admin account, and open **Admin**.

## Administrator access

Admin rights live in the database (`users.role`) and are checked on the server for every admin request. Registering with any particular email address never grants them. Create or promote an administrator only from the command line on the server:

```sh
python -m app.cli create-admin EMAIL    # new admin account
python -m app.cli promote EMAIL         # promote an existing user
```

## Layout

```
app/            Starlette backend (routes_auth, routes_chat, routes_admin, providers, settings_store, extract)
app/migrations/ Numbered SQL files, applied once each by `python -m app.cli migrate` (also run on startup)
static/         Single-page frontend (no build step): app.js, md.js, styles.css, logo.svg
tests/          pytest suite (31 tests) and a Playwright browser check in tests/e2e
deploy/         systemd unit, nginx config, backup script
```

## Tests

```sh
pip install -r requirements-dev.txt
python -m pytest -q          # unit and API tests against a fake AI vendor
sh tests/e2e/run.sh          # browser check (needs Playwright and Chromium)
```

The tests and the browser check use a local fake AI server. It exists only in `tests/` and is never used by the running product.

## More

- `FEATURES.md`: what is finished, what needs a key or service, and what is not built.
- `DEPLOYMENT.md`: domain, server, HTTPS, process management, backups, monitoring.
- `.env.example`: every setting, with comments.
