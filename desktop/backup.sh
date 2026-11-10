#!/bin/zsh
# Повний бекап БД + копія .env → backups/  (для переносу на інший ноут)
set -e
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/postgresql@16/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ ! -d "$ROOT_DIR/apps" ]; then
  [ -d "$HOME/dashboard/apps" ] && ROOT_DIR="$HOME/dashboard"
  [ -d "$HOME/fb-rent-dashboard/apps" ] && ROOT_DIR="$HOME/fb-rent-dashboard"
fi
cd "$ROOT_DIR/apps/api"
if [ ! -x "./.venv/bin/python" ]; then
  echo "Немає apps/api/.venv — спочатку запустіть ./setup_mac.sh"
  exit 1
fi
./.venv/bin/python -m app.cli backup
echo ""
echo "Готово. Для іншого ноута скопіюйте:"
echo "  1) теку проєкту (git clone або AirDrop)"
echo "  2) файл $ROOT_DIR/backups/latest.dump"
echo "  3) файл $ROOT_DIR/backups/env.transfer  →  перейменувати в .env на новому Mac"
echo "Потім на новому Mac: ./setup_mac.sh"
