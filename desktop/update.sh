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

echo "==> [2/5] Перевірка та запуск бази даних PostgreSQL..."
# Якщо у .env вказаний порт 5440 (Docker) або є встановлений Docker:
if grep -q ":5440" .env 2>/dev/null && command -v docker >/dev/null 2>&1; then
  if ! docker info >/dev/null 2>&1; then
    echo "🐳 Запускаємо Docker Desktop (зачекайте 10-20 секунд)..."
    open -a Docker || true
    for i in {1..30}; do
      if docker info >/dev/null 2>&1; then
        break
      fi
      sleep 2
    done
  fi
  if docker info >/dev/null 2>&1; then
    docker compose up -d db
    for i in {1..15}; do
      if nc -z 127.0.0.1 5440 >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi
fi

# Якщо ні 5440, ні 5432 не відповідають — піднімаємо локальний PostgreSQL через Homebrew
if ! nc -z 127.0.0.1 5440 >/dev/null 2>&1 && ! nc -z 127.0.0.1 5432 >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    if ! brew list postgresql@16 >/dev/null 2>&1; then
      echo "📦 Встановлення локального PostgreSQL 16 через Homebrew..."
      brew install postgresql@16
    fi
    brew services start postgresql@16 || true
    sleep 3
    export PATH="$(brew --prefix postgresql@16)/bin:$PATH"
    createuser -s fbrent 2>/dev/null || true
    createdb -O fbrent fbrent 2>/dev/null || true
    if [ -f .env ] && grep -q ":5440" .env; then
      sed -i '' 's|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://fbrent@localhost:5432/fbrent|' .env
    fi
  fi
fi

echo "==> [3/5] Оновлення Python-залежностей, міграцій та синхронізація локальної БД..."
cd "$ROOT_DIR/apps/api"
./.venv/bin/pip install -r requirements.txt
./.venv/bin/alembic upgrade head
if [ -f "$ROOT_DIR/desktop/db_snapshot.json.gz" ]; then
  ./.venv/bin/python3 -c "
from sqlalchemy import func, select
from app.core.db import SessionLocal
from app.models import Team, Account
from app.services.db_sync import import_snapshot
import os

with SessionLocal() as db:
    teams_cnt = db.scalar(select(func.count()).select_from(Team)) or 0
    accs_cnt = db.scalar(select(func.count()).select_from(Account)) or 0

if os.environ.get('FORCE_DB_SYNC') == '1' or teams_cnt < 5 or accs_cnt < 100:
    res = import_snapshot()
    print('✅ Перенесено повну локальну БД з основного ноутбука:', res)
else:
    print(f'ℹ️ Локальна БД вже заповнена (команд: {teams_cnt}, акаунтів: {accs_cnt}). Для примусового перезапису: FORCE_DB_SYNC=1 ./desktop/update.sh')
"
fi

echo "==> [4/5] Оновлення фронтенду та перезапуск сервісів (:8010 та :3010)..."
cd "$ROOT_DIR/apps/web"
npm install
lsof -ti :8010 | xargs kill -9 2>/dev/null || true
lsof -ti :3010 | xargs kill -9 2>/dev/null || true
sleep 1

echo "==> [5/5] Запуск FB Rent..."
exec "$ROOT_DIR/desktop/launch.sh"
