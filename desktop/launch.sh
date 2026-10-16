#!/bin/zsh
# Launcher script for FB Rent Desktop App (macOS)
set -e

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
ROOT_DIR="/Users/emojiestore/dashboard"
LOG_DIR="$ROOT_DIR/.logs"
mkdir -p "$LOG_DIR"

cd "$ROOT_DIR"

# 1. Ensure Postgres DB container is running on :5440
if ! nc -z 127.0.0.1 5440 >/dev/null 2>&1; then
  if command -v docker >/dev/null 2>&1; then
    docker compose up -d db >>"$LOG_DIR/db.log" 2>&1 || true
    sleep 2
  fi
fi

# 2. Ensure FastAPI backend is running on :8010 (with background 3-4h spend sync & 24h FBM reconciliation)
if ! nc -z 127.0.0.1 8010 >/dev/null 2>&1; then
  cd "$ROOT_DIR/apps/api"
  nohup ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 >>"$LOG_DIR/api.log" 2>&1 &
  cd "$ROOT_DIR"
fi

# 3. Ensure Next.js frontend is running on :3010
if ! nc -z 127.0.0.1 3010 >/dev/null 2>&1; then
  cd "$ROOT_DIR/apps/web"
  nohup npm run dev -- -p 3010 >>"$LOG_DIR/web.log" 2>&1 &
  cd "$ROOT_DIR"
fi

# Wait up to 8 seconds for web server to respond
for i in {1..16}; do
  if nc -z 127.0.0.1 3010 >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# 4. Open dedicated standalone Desktop App window (Chromeless App Mode if Chrome/Brave/Edge available, otherwise default browser)
APP_URL="http://localhost:3010/buyers"

if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args "--app=$APP_URL"
elif [ -d "/Applications/Brave Browser.app" ]; then
  open -na "Brave Browser" --args "--app=$APP_URL"
elif [ -d "/Applications/Microsoft Edge.app" ]; then
  open -na "Microsoft Edge" --args "--app=$APP_URL"
else
  open "$APP_URL"
fi
