#!/bin/zsh
# CLI & Desktop GitHub Auto-Updater + Restarter for FB Rent
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

echo "==> [1/5] Отримання свіжих оновлень з GitHub..."
if git remote get-url origin >/dev/null 2>&1; then
  git fetch origin --prune
  git reset --hard origin/main
else
  echo "GitHub remote 'origin' не налаштований."
fi

echo "==> [2/5] Перевірка PostgreSQL та оновлення Python-залежностей + міграцій БД..."
if ! nc -z 127.0.0.1 5432 >/dev/null 2>&1 && command -v brew >/dev/null 2>&1; then
  brew services start postgresql@16 || true
  sleep 2
fi

cd "$ROOT_DIR/apps/api"
./.venv/bin/pip install -r requirements.txt
./.venv/bin/alembic upgrade head

echo "==> [3/5] Оновлення залежностей фронтенду..."
cd "$ROOT_DIR/apps/web"
npm install

echo "==> [4/5] Перезапуск сервісів (API :8010 та Web :3010)..."
lsof -ti :8010 | xargs kill -9 2>/dev/null || true
lsof -ti :3010 | xargs kill -9 2>/dev/null || true
sleep 1

echo "==> [5/5] Запуск FB Rent..."
exec "$ROOT_DIR/desktop/launch.sh"
