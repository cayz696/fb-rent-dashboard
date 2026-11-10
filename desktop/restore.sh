#!/bin/zsh
# Відновлення БД з backups/latest.dump (або --file PATH)
set -e
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/postgresql@16/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ ! -d "$ROOT_DIR/apps" ]; then
  [ -d "$HOME/dashboard/apps" ] && ROOT_DIR="$HOME/dashboard"
  [ -d "$HOME/fb-rent-dashboard/apps" ] && ROOT_DIR="$HOME/fb-rent-dashboard"
fi

IF_EMPTY=""
FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --if-empty) IF_EMPTY="--if-empty" ;;
    --file) FILE="$2"; shift ;;
    *) echo "Невідомий аргумент: $1"; exit 1 ;;
  esac
  shift
done

cd "$ROOT_DIR/apps/api"
ARGS=(restore)
[ -n "$IF_EMPTY" ] && ARGS+=(--if-empty)
[ -n "$FILE" ] && ARGS+=(--file "$FILE")
./.venv/bin/python -m app.cli "${ARGS[@]}"
