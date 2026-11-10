# Перенесення FB Rent на інший Mac без втрати даних

Дані **не лежать у папці git**. Вони в Postgres (Docker-том `pgdata` на порту **5440**). Якщо скопіювати лише репозиторій — на новому ноуті буде порожня база.

## Що переносити (обов’язково)

| Файл | Навіщо |
|---|---|
| Репозиторій (`dashboard/`) | Код |
| `backups/latest.dump` | Уся БД: акаунти, картки, юзери, задачі, 2FA, Telegram-сесія |
| `backups/env.transfer` → покласти як `.env` | Ключі FBM, SECRET_KEY, токен bridge |

`.env` і `backups/` у git **не** комітяться.

## На старому ноуті

У дашборді: **Налаштування → «Зберегти копію БД»**.

Або в терміналі:

```bash
./desktop/pack.sh
```

На Робочому столі з’явиться `FB-Rent-transfer-….zip` (dump + env + коротка інструкція).

## На новому ноуті

1. Встановіть Docker Desktop (той самий варіант, що на основному Mac) або Homebrew PostgreSQL.
2. Скопіюйте репозиторій (`git clone` або AirDrop папки).
3. Розпакуйте архів:
   - `fbrent.dump` → `dashboard/backups/latest.dump`
   - `env.transfer` → `dashboard/.env`
4. Запустіть:

```bash
chmod +x setup_mac.sh desktop/*.sh
./setup_mac.sh
./desktop/launch.sh
```

`setup_mac.sh` підніме Postgres, накатить міграції і **сам відновить dump, якщо база порожня**. Існуючі дані не затирає (`--if-empty`).

Логін і 2FA залишаються як були: користувачі їдуть у dump.

## Оновлення коду (не даних)

```bash
./desktop/update.sh
```

Спочатку робить бекап, потім `git pull --ff-only` (без `reset --hard`) і міграції. Базу не перезаписує.

## AdsPower / bridge

Міст AdsPower лишається на машині, де встановлений AdsPower. Другий ноут покаже дашборд і всі дані; статус мосту буде «офлайн», поки там не запущено `apps/bridge`.

## Примусове відновлення (затирає поточну БД)

```bash
./desktop/restore.sh
```

Без `--if-empty` база буде замінена вмістом `backups/latest.dump`.
