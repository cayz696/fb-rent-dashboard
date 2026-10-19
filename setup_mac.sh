#!/bin/bash
# ==============================================================================
# Skull Partners FB Rent Dashboard - Повний автоматичний інсталятор для macOS
# ==============================================================================
set -e

echo "🚀 Початок автоматичного налаштування Skull Partners FB Rent..."

# 1. Перевірка Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "📦 Встановлення Homebrew (потрібно для бази та середовища)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -d "/opt/homebrew/bin" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
fi

# 2. Встановлення легкого PostgreSQL та Node.js без Docker
echo "📦 Встановлення залежностей (PostgreSQL, Python, Node)..."
brew install postgresql@16 node python@3.11 || true

# Запуск служби бази даних
echo "🗄️ Запуск локальної бази даних..."
brew services start postgresql@16 || true
sleep 3

# Створення користувача та бази fbrent (якщо ще немає)
createuser -s fbrent 2>/dev/null || true
createdb -O fbrent fbrent 2>/dev/null || true

# 3. Налаштування .env
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "⚙️ Створення конфігурації .env..."
  cat << 'ENVEOF' > .env
APP_ENV=dev
APP_TZ=Europe/Kyiv
SECRET_KEY=skull-partners-secret-key-prod-0123456789abcdef
SESSION_TTL_HOURS=24
DATABASE_URL=postgresql+psycopg://fbrent@localhost:5432/fbrent
NEXT_PUBLIC_API_URL=
CLOVER_SPEND_SECRET=dev-clover-secret-change-me
BRIDGE_TOKEN=dev-bridge-token-change-me
FBM_API_URL=https://fbm-pay.com
FBM_API_KEY=fbm_47DcRUwVJ4MZxMhSN7w9HZhCxEQf9hMtul9Z6C85dQvE6rbA
FBM_PROXY=http://skullpartners:kbtVCtAZjs@95.135.50.46:50100
GOOGLE_SHEETS_BUYERS_WEBHOOK_URL=https://script.google.com/macros/s/AKfycbw_MEkPB3eQOV-mJheXapWPGFygbFRxD4nZ2_euPg7eFXcqdLFbTwKyT7p2wsyYSMCd9w/exec
ENVEOF
fi

# 4. Налаштування API (Python)
echo "🐍 Налаштування Backend API..."
cd "$ROOT_DIR/apps/api"
PY_BIN="$(brew --prefix python@3.11 2>/dev/null)/bin/python3"
if [ ! -x "$PY_BIN" ]; then
  PY_BIN="python3"
fi

rm -rf .venv
"$PY_BIN" -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
./.venv/bin/alembic upgrade head

# 5. Налаштування Web (Node.js)
echo "🌐 Збірка Web Frontend..."
cd "$ROOT_DIR/apps/web"
npm install
npm run build

# 6. Встановлення ярлика в Програми
echo "🖥️ Встановлення додатку FB Rent..."
cd "$ROOT_DIR"
cp -r "FB Rent.app" /Applications/ 2>/dev/null || true

echo ""
echo "========================================================="
echo "✅ ВСЕ ВСТАНОВЛЕНО ТА НАЛАШТОВАНО!"
echo "Тепер просто відкрийте Launchpad або Програми і запустіть:"
echo "👉 FB Rent (додаток із неоновим черепом)"
echo "========================================================="
