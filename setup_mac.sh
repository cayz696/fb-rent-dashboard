#!/bin/bash
# Skull Partners FB Rent — інсталятор для macOS (перший запуск або новий ноут).
# Секрети НЕ генерує з хардкоду: бере backups/env.transfer або існуючий .env.
set -e

echo "==> Налаштування Skull Partners FB Rent"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/postgresql@16/bin:/usr/local/bin:$PATH"

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "Встановлення Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -d "/opt/homebrew/bin" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
fi

# 2. .env: спочатку перенесення з іншого ноута, інакше шаблон
if [ ! -f .env ]; then
  if [ -f backups/env.transfer ]; then
    echo "Копіюю backups/env.transfer → .env"
    cp backups/env.transfer .env
  elif [ -f .env.example ]; then
    echo "Немає .env — створюю з .env.example (потрібно буде вписати ключі FBM/SECRET_KEY)"
    cp .env.example .env
    if command -v python3 >/dev/null 2>&1; then
      KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
      if grep -q '^SECRET_KEY=$' .env 2>/dev/null || grep -q '^SECRET_KEY=\s*$' .env; then
        sed -i '' "s|^SECRET_KEY=.*|SECRET_KEY=$KEY|" .env
      fi
    fi
    if ! grep -q '^DATABASE_URL=' .env || grep -q '^DATABASE_URL=$' .env; then
      if command -v docker >/dev/null 2>&1; then
        # значення підставить блок нижче після docker
        :
      fi
    fi
  else
    echo "Немає ні .env, ні .env.example"
    exit 1
  fi
fi

# 3. Postgres: Docker :5440 (як на основному ноуті) або Homebrew :5432
DB_OK=0
if command -v docker >/dev/null 2>&1; then
  if ! docker info >/dev/null 2>&1; then
    echo "Запускаю Docker Desktop..."
    open -a Docker || true
    for i in $(seq 1 30); do
      docker info >/dev/null 2>&1 && break
      sleep 2
    done
  fi
  if docker info >/dev/null 2>&1; then
    # Якщо в .env ще порожній DATABASE_URL — ставимо docker-порт
    if grep -q '^DATABASE_URL=$' .env 2>/dev/null || ! grep -q '^DATABASE_URL=.\+' .env; then
      grep -q '^POSTGRES_USER=' .env || echo 'POSTGRES_USER=fbrent' >> .env
      grep -q '^POSTGRES_PASSWORD=' .env || echo 'POSTGRES_PASSWORD=fbrent' >> .env
      grep -q '^POSTGRES_DB=' .env || echo 'POSTGRES_DB=fbrent' >> .env
      # не перезаписуємо непорожній URL
      if ! grep -q '^DATABASE_URL=.\+' .env; then
        echo 'DATABASE_URL=postgresql+psycopg://fbrent:fbrent@localhost:5440/fbrent' >> .env
      fi
    fi
    docker compose up -d db
    for i in $(seq 1 30); do
      if nc -z 127.0.0.1 5440 >/dev/null 2>&1; then DB_OK=1; break; fi
      sleep 1
    done
  fi
fi

if [ "$DB_OK" -eq 0 ]; then
  echo "Docker недоступний — ставлю локальний PostgreSQL 16"
  brew install postgresql@16 node python@3.12 || brew install postgresql@16 node python3 || true
  brew services start postgresql@16 || true
  sleep 3
  export PATH="$(brew --prefix postgresql@16 2>/dev/null)/bin:$PATH"
  createuser -s fbrent 2>/dev/null || true
  createdb -O fbrent fbrent 2>/dev/null || true
  if grep -q ':5440' .env 2>/dev/null; then
    sed -i '' 's|localhost:5440|localhost:5432|g' .env
  fi
  if ! grep -q '^DATABASE_URL=.\+' .env; then
    echo 'DATABASE_URL=postgresql+psycopg://fbrent@localhost:5432/fbrent' >> .env
  fi
fi

brew list node >/dev/null 2>&1 || brew install node || true

# 4. API
echo "==> Backend"
cd "$ROOT_DIR/apps/api"
if [ ! -x .venv/bin/python ]; then
  PY_BIN="$(brew --prefix python@3.12 2>/dev/null)/bin/python3"
  [ -x "$PY_BIN" ] || PY_BIN="$(brew --prefix python@3.11 2>/dev/null)/bin/python3"
  [ -x "$PY_BIN" ] || PY_BIN="python3"
  "$PY_BIN" -m venv .venv
fi
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt
./.venv/bin/alembic upgrade head

# 5. Відновити дані з бекапа, якщо БД порожня
if [ -f "$ROOT_DIR/backups/latest.dump" ] || [ -f "$ROOT_DIR/backups/latest.json.gz" ]; then
  echo "==> Відновлення даних з backups/"
  ./.venv/bin/python -m app.cli restore --if-empty || true
fi

# 6. Web
echo "==> Frontend"
cd "$ROOT_DIR/apps/web"
npm install
npm run build || true

# 7. Ярлик
cd "$ROOT_DIR"
if [ -d "FB Rent.app" ]; then
  cp -R "FB Rent.app" /Applications/ 2>/dev/null || true
fi

echo ""
echo "=============================================="
echo "Готово. Запуск:  ./desktop/launch.sh"
echo "або Програми → FB Rent"
echo "Бекап перед переносом: ./desktop/pack.sh"
echo "Інструкція: docs/TRANSFER.md"
echo "=============================================="
