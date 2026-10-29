# Deploying ARNET AI on an Ubuntu server

These steps assume Ubuntu 22.04 or newer, a user with sudo, and a domain **you have already bought**. Do not announce the site until the checks in step 9 pass.

## 1. DNS

At your domain registrar or DNS host, create:

- an `A` record for `example.com` pointing to the server's IPv4 address
- an `A` record for `www.example.com` pointing to the same address (and `AAAA` records if the server has IPv6)

Wait for it to resolve: `dig +short example.com` should print your server's address.

## 2. Server setup

```sh
sudo apt update && sudo apt install -y python3-venv nginx certbot python3-certbot-nginx ufw
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
sudo useradd --system --create-home --shell /usr/sbin/nologin arnet
```

## 3. Install the app

```sh
sudo mkdir -p /opt/arnet-ai && sudo chown arnet:arnet /opt/arnet-ai
# copy the project into /opt/arnet-ai (scp, rsync or git), then:
sudo -u arnet python3 -m venv /opt/arnet-ai/.venv
sudo -u arnet /opt/arnet-ai/.venv/bin/pip install -r /opt/arnet-ai/requirements.txt
```

## 4. Environment variables

```sh
sudo -u arnet cp /opt/arnet-ai/.env.example /opt/arnet-ai/.env
sudo -u arnet nano /opt/arnet-ai/.env
sudo chmod 600 /opt/arnet-ai/.env
```

Set at least `AI_API_KEY`, `APP_BASE_URL=https://example.com`, `COOKIE_SECURE=true`, `TRUST_PROXY=true`. Add the image, search and SMTP values you want. The `.env` file holds secrets: keep it out of git and out of backups that others can read.

## 5. Database

SQLite needs no server. The file is created in `/opt/arnet-ai/data`. Apply migrations and create the owner account:

```sh
cd /opt/arnet-ai
sudo -u arnet sh -c 'set -a; . ./.env; set +a; .venv/bin/python -m app.cli migrate'
sudo -u arnet sh -c 'set -a; . ./.env; set +a; .venv/bin/python -m app.cli create-admin you@example.com'
```

Migrations also run automatically each time the app starts.

## 6. Process management (systemd)

```sh
sudo cp /opt/arnet-ai/deploy/arnet.service /etc/systemd/system/arnet.service
sudo systemctl daemon-reload
sudo systemctl enable --now arnet
sudo systemctl status arnet
journalctl -u arnet -f          # live logs
```

The unit runs one worker on purpose (see FEATURES.md).

## 7. Reverse proxy

```sh
sudo cp /opt/arnet-ai/deploy/nginx.conf /etc/nginx/sites-available/arnet
sudo nano /etc/nginx/sites-available/arnet          # replace example.com with your domain
sudo ln -s /etc/nginx/sites-available/arnet /etc/nginx/sites-enabled/arnet
sudo nginx -t && sudo systemctl reload nginx
```

## 8. HTTPS certificate

```sh
sudo certbot --nginx -d example.com -d www.example.com
sudo systemctl status certbot.timer     # renewal runs automatically
```

## 9. Verify before you call it live

- `curl -I https://example.com/` returns `200`, and `curl -I http://example.com/` redirects to `https://`.
- `curl https://example.com/api/health` returns `{"status":"ok"}`.
- Sign in as the admin, open **Admin, Service health**: "AI provider" should say the key is set. That only proves the key is present, not that it is valid, so the chat message below is the real test. If it says the key is missing, fix `.env` and `sudo systemctl restart arnet`.
- Send one chat message, watch it stream, reload and confirm it is saved.
- Register a second test account and confirm it cannot see the first account's chats or open **Admin**.
- Check the footer, About and Contact pages, and tap the email and WhatsApp links.

## 10. Backups

```sh
sudo -u arnet crontab -e
# add:  15 2 * * * /opt/arnet-ai/deploy/backup.sh
```

The script writes a consistent copy of the database (and images) to `/var/backups/arnet` and keeps 14 days. Copy those files off the server regularly (another machine or object storage). Practise a restore once: stop the service, copy a backup over `data/arnet.sqlite3`, start the service.

## 11. Monitoring

- **Inside the app:** Admin shows service health, the AI request log and an error log.
- **Outside the app:** point a free uptime monitor (for example UptimeRobot or Better Stack) at `https://example.com/api/health` and alert yourself by email or phone.
- **Server:** `journalctl -u arnet`, `/var/log/nginx/error.log`, and `df -h` now and then for disk space.
- **Updates:** `sudo apt upgrade` monthly; after updating the app run `pip install -r requirements.txt`, then `sudo systemctl restart arnet`.
