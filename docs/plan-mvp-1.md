# План MVP-1: облік

Мета (ТЗ §10): логін з 2FA, CRUD акаунтів/клієнтів/постачальників/партій, статус-машина з валідацією, журнал подій, дашборд і картка акаунта в стилі Obsidian.
Критерій приймання: акаунт проходить `purchased → … → issued`, кожен крок у журналі з автором; недозволений перехід → 409.

## Рішення
- БД: PostgreSQL 16 у Docker (порт хоста **5440**, щоб не конфліктувати з локальним PG 14). Синхронний SQLAlchemy 2 + psycopg 3.
- Одна початкова міграція Alembic створює **усі** таблиці з §4 (спільна схема), API MVP-1 працює з підмножиною.
- Сесія: JWT у httpOnly-cookie (термін `SESSION_TTL_HOURS`). Вхід у два кроки: пароль → pre-token (5 хв) → TOTP. Якщо TOTP ще не налаштований — крок налаштування (QR/secret) при першому вході. Без 2FA сесію не видаємо.
- Секрет TOTP **користувача системи** зберігається в `users.totp_secret` (заборона в §4 стосується даних акаунтів FB).
- Ролі: `admin` — все; `operator` — етапи, без видачі (`issued`), без фінансових полів (`purchase_cost` приховується); `viewer` — тільки читання.
- Код акаунта `FB-0001…` — Postgres sequence, генерується при створенні.
- Web: Next.js 15, Tailwind 4, SWR; запити через rewrite `/api/*` → FastAPI (same-origin cookies). UI-компоненти власні в стилі shadcn (`cn` + cva), можна підмінити на shadcn CLI пізніше.

## API (apps/api)
| Метод | Шлях | Роль |
|---|---|---|
| POST | /api/auth/login, /auth/2fa/setup, /auth/2fa/verify, /auth/logout | — |
| GET | /api/me | усі |
| GET/POST/PATCH | /api/accounts, /api/accounts/{id} | read: усі, write: admin/operator |
| POST | /api/accounts/{id}/transition | admin/operator (`issued` — тільки admin) |
| GET | /api/accounts/{id}/events, /api/events | усі |
| CRUD | /api/clients, /api/suppliers, /api/batches | write: admin |
| GET | /api/dashboard, /api/signals | усі |

Статус-машина: `app/services/state_machine.py` (чиста функція, без БД) + `app/services/accounts.py` (застосування, події, `check_until`). Недозволений перехід/порушення правил → **409**.

## Файли
- `apps/api/app/{core/config,core/db,core/security}.py`, `models/*.py`, `schemas/*.py`, `api/routes/*.py`, `main.py`, `cli.py` (create-user, seed-demo)
- `apps/api/alembic/versions/0001_initial.py`
- `apps/api/tests/`: статус-машина, auth+2FA, сценарій приймання MVP-1
- `apps/web/src/app/(auth)/login`, `(app)/{dashboard,accounts,accounts/[id],kanban,clients,suppliers,events,…}`, `components/*`, `lib/{api,stages}.ts`

## Поза MVP-1 (заглушки «Скоро»)
Заявки/Telegram (MVP-2), Clover-спенд і графіки (MVP-3), bridge (MVP-4), агент (MVP-5), фінанси. KPI спенду на дашборді беруться з `spend_snapshots` (поки порожньо → «—»).
