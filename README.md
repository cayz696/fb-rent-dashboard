# FB Rent — облік і видача рекламних акаунтів

ТЗ: [docs/TZ.md](docs/TZ.md) · Дизайн (тема **Obsidian Pro**): [docs/design/visual-concepts.html](docs/design/visual-concepts.html), токени: `apps/web/src/styles/tokens.css`

## Структура
| Шлях | Що |
|---|---|
| `apps/web` | Next.js 15 + TS + Tailwind + shadcn/ui. Маршрути `src/app/(app)/*` = екрани з розділу 8 ТЗ |
| `apps/api` | FastAPI, SQLAlchemy 2, Alembic. `services/state_machine.py` — статус-машина, `integrations/clover_mapper.py` — парсер Clover (MVP-3), `workers/signals.py` — сигнали кожні 15 хв |
| `apps/bot` | aiogram 3, Telegram-бот (MVP-2) |
| `apps/bridge` | Агент на машині з AdsPower, WS → сервер (MVP-4) |
| `agent/skills` | Опис інструментів ШІ-агента, по файлу на інструмент (MVP-5) |
| `docs` | ТЗ, дизайн-референси, `plan-mvp-N.md` перед кодом кожного етапу |

## Порядок роботи
MVP-1 облік → MVP-2 Telegram → MVP-3 Clover → MVP-4 Bridge → MVP-5 ШІ-агент. Перед кожним етапом — `docs/plan-mvp-N.md`.

## Локальний запуск (dev)
```bash
cp .env.example .env            # заповнити SECRET_KEY, DATABASE_URL, POSTGRES_* (див. docs/WORKLOG.md щодо портів)
docker compose up -d db         # Postgres 16 на :5440
cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli create-user admin "Ім'я" admin     # 2FA налаштується при першому вході
.venv/bin/python -m app.cli seed-demo                            # (опційно) демо-партії й клієнти
.venv/bin/uvicorn app.main:app --port 8010 --reload
cd ../web && npm install && npm run dev                          # http://localhost:3010
```
Тести API: `cd apps/api && .venv/bin/python -m pytest` (створює окрему БД `fbrent_test`).

## Статус
Див. [docs/WORKLOG.md](docs/WORKLOG.md).
