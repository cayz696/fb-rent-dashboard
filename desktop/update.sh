#!/bin/zsh
# CLI & Desktop GitHub Auto-Updater for FB Rent
set -e

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
ROOT_DIR="/Users/emojiestore/dashboard"
cd "$ROOT_DIR"

echo "==> [FB Rent] Перевірка оновлень з GitHub..."
if git remote get-url origin >/dev/null 2>&1; then
  git fetch origin --prune
  git pull --ff-only
else
  echo "GitHub remote 'origin' ще не налаштований. Вкажіть URL у Налаштуваннях дашборду."
fi

echo "==> [FB Rent] Застосування міграцій бази даних..."
cd "$ROOT_DIR/apps/api"
./.venv/bin/alembic upgrade head

echo "==> [FB Rent] Оновлення завершено успішно!"
