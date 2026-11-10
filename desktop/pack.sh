#!/bin/zsh
# Збирає архів на Робочий стіл: dump + .env. Нічого не кладе в git.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ ! -d "$ROOT_DIR/apps" ]; then
  [ -d "$HOME/dashboard/apps" ] && ROOT_DIR="$HOME/dashboard"
  [ -d "$HOME/fb-rent-dashboard/apps" ] && ROOT_DIR="$HOME/fb-rent-dashboard"
fi

"$ROOT_DIR/desktop/backup.sh"

STAMP="$(date +%Y%m%d-%H%M)"
OUT="$HOME/Desktop/FB-Rent-transfer-$STAMP"
mkdir -p "$OUT"
cp "$ROOT_DIR/backups/latest.dump" "$OUT/fbrent.dump"
if [ -f "$ROOT_DIR/backups/env.transfer" ]; then
  cp "$ROOT_DIR/backups/env.transfer" "$OUT/env.transfer"
fi
cp "$ROOT_DIR/docs/TRANSFER.md" "$OUT/README.txt" 2>/dev/null || true
cat > "$OUT/ЯК ВІДНОВИТИ.txt" << 'EOF'
1. На новому Mac скопіюйте репозиторій (git clone або скопіюйте папку dashboard).
2. Покладіть fbrent.dump у dashboard/backups/latest.dump
   і env.transfer у dashboard/.env  (саме .env у корені проєкту).
3. Запустіть:  ./setup_mac.sh
4. Відкрийте FB Rent.app — дані мають бути ті самі (акаунти, картки, юзери, задачі).
EOF

ZIP="$HOME/Desktop/FB-Rent-transfer-$STAMP.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$OUT" "$ZIP"
echo ""
echo "Архів для іншого ноута: $ZIP"
echo "Папка: $OUT"
