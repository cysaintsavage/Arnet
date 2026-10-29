#!/bin/sh
# Daily backup of the database and uploads. Example cron entry (as the arnet user):
#   15 2 * * * /opt/arnet-ai/deploy/backup.sh
# Copy the resulting files off the server too (another machine or object storage). A backup on the same disk is not enough.
set -eu
APP=/opt/arnet-ai
DEST="${BACKUP_DIR:-/var/backups/arnet}"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"
# SQLite's own backup command gives a consistent copy while the app is running.
"$APP/.venv/bin/python" - "$APP/data/arnet.sqlite3" "$DEST/arnet-$STAMP.sqlite3" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
# Generated images are stored as files next to the database (document text is inside the database).
if [ -d "$APP/data/images" ]; then tar -czf "$DEST/images-$STAMP.tar.gz" -C "$APP/data" images; fi
# Keep 14 days.
find "$DEST" -type f -mtime +14 -delete
echo "Backup written to $DEST ($STAMP)"
