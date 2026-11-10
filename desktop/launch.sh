#!/bin/zsh
# Launcher script for FB Rent Desktop App (macOS)
set -e

export PATH="/opt/homebrew/bin:/opt/homebrew/opt/postgresql@16/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -d "$ROOT_DIR/apps" ]; then
  if [ -d "$HOME/fb-rent-dashboard/apps" ]; then
    ROOT_DIR="$HOME/fb-rent-dashboard"
  elif [ -d "$HOME/dashboard/apps" ]; then
    ROOT_DIR="$HOME/dashboard"
  fi
fi

LOG_DIR="$ROOT_DIR/.logs"
mkdir -p "$LOG_DIR"
cd "$ROOT_DIR"

if [ ! -f .env ] && [ -f backups/env.transfer ]; then
  cp backups/env.transfer .env
fi

# 1. Postgres: Docker :5440 або Homebrew :5432
if ! nc -z 127.0.0.1 5432 >/dev/null 2>&1 && ! nc -z 127.0.0.1 5440 >/dev/null 2>&1; then
  if grep -q ":5440" .env 2>/dev/null && command -v docker >/dev/null 2>&1; then
    if ! docker info >/dev/null 2>&1; then
      open -a Docker || true
      for i in {1..20}; do
        docker info >/dev/null 2>&1 && break
        sleep 2
      done
    fi
    docker compose up -d db >>"$LOG_DIR/db.log" 2>&1 || true
    sleep 2
  fi
  if ! nc -z 127.0.0.1 5440 >/dev/null 2>&1 && command -v brew >/dev/null 2>&1; then
    brew services start postgresql@16 >>"$LOG_DIR/db.log" 2>&1 || true
    sleep 2
  fi
fi

# 2. Міграції + авто-відновлення, якщо БД порожня, а бекап є
cd "$ROOT_DIR/apps/api"
if [ -x "./.venv/bin/pip" ]; then
  ./.venv/bin/pip install -q -r requirements.txt >>"$LOG_DIR/api.log" 2>&1 || true
  ./.venv/bin/alembic upgrade head >>"$LOG_DIR/api.log" 2>&1 || true
  if [ -f "$ROOT_DIR/backups/latest.dump" ] || [ -f "$ROOT_DIR/backups/latest.json.gz" ]; then
    ./.venv/bin/python -m app.cli restore --if-empty >>"$LOG_DIR/api.log" 2>&1 || true
  fi
fi

if ! nc -z 127.0.0.1 8010 >/dev/null 2>&1; then
  nohup ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 >>"$LOG_DIR/api.log" 2>&1 &
fi
cd "$ROOT_DIR"

# 3. Next.js
if ! nc -z 127.0.0.1 3010 >/dev/null 2>&1; then
  cd "$ROOT_DIR/apps/web"
  nohup npm run dev -- -p 3010 >>"$LOG_DIR/web.log" 2>&1 &
  cd "$ROOT_DIR"
fi

for i in {1..20}; do
  if nc -z 127.0.0.1 3010 >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# 4. Тихе оновлення бекапа, якщо останній старший за 24 год
if [ -x "$ROOT_DIR/apps/api/.venv/bin/python" ]; then
  NEED_BACKUP=1
  if [ -f "$ROOT_DIR/backups/latest.dump" ]; then
    AGE=$(( $(date +%s) - $(stat -f %m "$ROOT_DIR/backups/latest.dump") ))
    [ "$AGE" -lt 86400 ] && NEED_BACKUP=0
  fi
  if [ "$NEED_BACKUP" -eq 1 ]; then
    (cd "$ROOT_DIR/apps/api" && ./.venv/bin/python -m app.cli backup >>"$LOG_DIR/backup.log" 2>&1) &
  fi
fi

APP_URL="http://localhost:3010/dashboard"
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args "--app=$APP_URL"
elif [ -d "/Applications/Brave Browser.app" ]; then
  open -na "Brave Browser" --args "--app=$APP_URL"
elif [ -d "/Applications/Microsoft Edge.app" ]; then
  open -na "Microsoft Edge" --args "--app=$APP_URL"
else
  open "$APP_URL"
fi
