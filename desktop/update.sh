#!/bin/zsh
# Оновлення коду на машині з дашбордом. Не викликається з браузера.
set -e

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "==> [FB Rent] Перевірка оновлень з GitHub..."
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "Remote origin не налаштований. Додайте його локально: git remote add origin https://github.com/<org>/<repo>.git"
  exit 1
fi

url="$(git remote get-url origin)"
case "$url" in
  https://github.com/*|git@github.com:*) ;;
  *)
    echo "Remote має бути репозиторієм github.com, зараз: $url"
    exit 1
    ;;
esac

git fetch origin --prune
git pull --ff-only

echo "==> [FB Rent] Застосування міграцій бази даних..."
cd "$ROOT_DIR/apps/api"
./.venv/bin/alembic upgrade head

echo "==> [FB Rent] Оновлення завершено успішно!"
