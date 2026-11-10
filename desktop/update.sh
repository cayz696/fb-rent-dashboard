#!/bin/zsh
# Оновлення коду з GitHub БЕЗ втрати БД. git reset --hard більше не використовується.
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

cd "$ROOT_DIR"

echo "==> [1/5] Бекап БД перед оновленням коду..."
if [ -x "$ROOT_DIR/apps/api/.venv/bin/python" ]; then
  (cd "$ROOT_DIR/apps/api" && ./.venv/bin/python -m app.cli backup) || echo "Бекап не вдався — продовжую оновлення коду"
fi

echo "==> [2/5] git pull --ff-only (локальні дані в backups/ не чіпаємо)"
if git remote get-url origin >/dev/null 2>&1; then
  git fetch origin --prune
  git pull --ff-only origin HEAD || git pull --ff-only origin main
else
  echo "GitHub remote 'origin' не налаштований."
fi

echo "==> [3/5] Postgres..."
if grep -q ":5440" .env 2>/dev/null && command -v docker >/dev/null 2>&1; then
  if ! docker info >/dev/null 2>&1; then
    open -a Docker || true
    for i in {1..30}; do
      docker info >/dev/null 2>&1 && break
      sleep 2
    done
  fi
  if docker info >/dev/null 2>&1; then
    docker compose up -d db
    for i in {1..15}; do
      nc -z 127.0.0.1 5440 >/dev/null 2>&1 && break
      sleep 1
    done
  fi
fi

if ! nc -z 127.0.0.1 5440 >/dev/null 2>&1 && ! nc -z 127.0.0.1 5432 >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew list postgresql@16 >/dev/null 2>&1 || brew install postgresql@16
    brew services start postgresql@16 || true
    sleep 3
    export PATH="$(brew --prefix postgresql@16)/bin:$PATH"
    createuser -s fbrent 2>/dev/null || true
    createdb -O fbrent fbrent 2>/dev/null || true
  fi
fi

echo "==> [4/5] Залежності та міграції (без перезапису даних)"
cd "$ROOT_DIR/apps/api"
./.venv/bin/pip install -r requirements.txt
./.venv/bin/alembic upgrade head
# Відновлюємо ТІЛЬКИ порожню БД (новий ноут). Існуючі дані не чіпаємо.
./.venv/bin/python -m app.cli restore --if-empty || true

echo "==> [5/5] Frontend і запуск"
cd "$ROOT_DIR/apps/web"
npm install
lsof -ti :8010 | xargs kill -9 2>/dev/null || true
lsof -ti :3010 | xargs kill -9 2>/dev/null || true
sleep 1
exec "$ROOT_DIR/desktop/launch.sh"
