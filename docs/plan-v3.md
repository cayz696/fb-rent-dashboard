# План v3: Юзери та Команди FBM, Фіксація спенду (3–4 год), Таблиці, Обмежені учотки, Звітність (Точка прибутку) та Десктоп-додаток

Дата: 16.10.2026
Статус: На паузі — `spec-share-access.md` (Розшарити доступ BM) та `spec-v2.md` (пул Кінги / робота через проксі).

---

## 1. Міграція БД (`0009_v3_buyers_sheets_reports_permissions.py`)

1. **Розширення `users`**:
   - `allowed_sections`: `ARRAY(String)` (nullable) — список дозволених розділів дашборду для облікових записів з обмеженими правами (якщо `None` або `role == 'admin'` — доступні всі розділи За роллю).
2. **Таблиця `teams` (Команди та їхні Google-таблиці)**:
   - `id` (UUID PK)
   - `name` (String, unique) — напр. `CPA Samurai Team 298`, `Budget Samurai Team 300`, `Clover Group 297`, `R2D100`, `T5`
   - `sheet_url` (Text, nullable) — посилання на Google-таблицю команди
   - `sheet_gid` (String, nullable) — gid вкладки (за замовч. `0`)
   - `sheet_balance` (Numeric(12,2), nullable) — баланс команди, зчитаний з таблиці (напр. `$2,283.48`)
   - `topup_total` (Numeric(12,2), nullable) — «Спенд пополнено» з таблиці
   - `spend_total_sheet` (Numeric(12,2), nullable) — «Спенд потрачено» з таблиці
   - `fee_percent` (Numeric(5,2), default `7.00`) — % комісії команди
   - `last_sheet_sync` (DateTime(tz), nullable)
   - `notes` (Text, nullable)
   - `created_at` (DateTime(tz))
3. **Таблиця `buyers` (Юзери / Баєри без дублів)**:
   - `id` (UUID PK)
   - `name` (String(128), unique) — ім'я юзера (напр. `VSamurai`, `WebBubka`, `WebAX`, `Graf`, `WebTxmmy`)
   - `team_id` (UUID FK -> `teams.id`, nullable, index)
   - `is_priority` (Boolean, default `False`) — галочка пріоритету (піднімає вгору списку)
   - `fbm_owner` (String(128), nullable) — власник у FBM (`Akiyama`, `Igor SkullPartners`)
   - `accounts_count` (Integer, nullable) — к-сть кабінетів (стовпець T1 з таблиці)
   - `notes` (Text, nullable)
   - `created_at` (DateTime(tz))
4. **Таблиця `card_spend_logs` (Фіксація спенду по картках кожні 3–4 години)**:
   - `id` (BigInteger Identity PK)
   - `card_id` (String(64), index)
   - `last4` (String(8))
   - `card_name` (Text)
   - `buyer_id` (UUID FK -> `buyers.id`, nullable, index)
   - `team_id` (UUID FK -> `teams.id`, nullable, index)
   - `account_name` (String(64)) — рахунок FBM (`Account1_US`, `Account1`)
   - `account_balance` (Numeric(12,2), nullable)
   - `spend_cumulative` (Numeric(12,2)) — `stats.spend` картки на момент знімка
   - `spend_delta` (Numeric(12,2)) — дельта з попередньої фіксації
   - `date` (Date, index) — дата в `Europe/Kyiv`
   - `recorded_at` (DateTime(tz), index)
5. **Таблиця `buyer_daily_spends` (Поденний спенд юзера)**:
   - `id` (BigInteger Identity PK)
   - `buyer_id` (UUID FK -> `buyers.id`, index)
   - `date` (Date, index)
   - `spend_fbm` (Numeric(12,2), default `0`) — накопичена дельта по картках FBM за день
   - `spend_sheet` (Numeric(12,2), nullable) — значення з Google-таблиці за цей день
   - `updated_at` (DateTime(tz))
6. **Таблиця `fbm_reconciliations` (Добова звірка розбіжностей з FBM Cards)**:
   - `id` (UUID PK)
   - `checked_at` (DateTime(tz))
   - `status` (String(32)) — `ok` | `discrepancy`
   - `db_total_spend` (Numeric(12,2))
   - `fbm_total_spend` (Numeric(12,2))
   - `diff_amount` (Numeric(12,2))
   - `discrepancies` (JSONB) — деталі розбіжностей по картках/юзерах
7. **Таблиці звітності (`expense_categories`, `expenses`)**:
   - `expense_categories`: `id` (UUID PK), `name` (String(128), unique), `color` (String(32)), `created_at`
   - `expenses`: `id` (UUID PK), `category_id` (UUID FK -> `expense_categories.id`), `amount` (Numeric(12,2)), `spent_at` (Date, index), `description` (Text), `created_by` (String(64)), `created_at`

---

## 2. Бекенд-сервіси та API (`apps/api`)

1. **`services/buyers_sync.py`**:
   - Детермінований парсер назв карток FBM → виділення Команди (`CPA Samurai Team 298`, `Budget Samurai Team 300`, `Clover Group 297`, `R2D100`, `T5`) та канонічного імені Юзера (`WebAX4` → `WebAX`, `WebTxmmy2` → `WebTxmmy`, `WebGraf3` → `Graf` тощо) з перевіркою дублів (case-insensitive).
   - Фіксація спенду кожні 3–4 год (`record_card_spends(db)`): оновлює знімок FBM, записує `card_spend_logs`, оновлює `buyer_daily_spends`.
   - Добова звірка (`reconcile_fbm_spend(db)`): порівнює зафіксовані суми по картках у БД з кабінетом FBM (`stats.spend` та `/payments`), формує звіт і сповіщення при розбіжностях.
   - Парсинг Google-таблиць команд по прямому посиланню CSV (`sync_team_sheet(db, team)`): читає баланс команди (`$2,283.48`), суми поповнень/витрат, список юзерів без дублів та їхній поденний спенд по стовпцях дат (`1/10`, `2/10`...).
2. **Розширення сигналів та сповіщень (`services/signals.py`, `api/routes/notifications.py`)**:
   - Сигнал `low_balance`: якщо баланс рахунку FBM (`Account1`, `Account1_US`) або баланс команди з таблиці `< $1000` (`warning`) або `< $0` (`danger` — мінусовий баланс).
   - Сигнал `fbm_discrepancy`: якщо добова звірка виявила розбіжність між дашбордом і кабінетом FBM Cards.
3. **Нові маршрути API**:
   - `/api/buyers`: список юзерів (сортування: пріоритетні зверху + за спендом/назвою/кількістю карток, фільтр по команді), створення вручну з перевіркою дублів, перемикання галочки пріоритету (`PATCH /api/buyers/{id}`), парсинг нових юзерів із FBM (`POST /api/buyers/parse-fbm`), фіксація спенду (`POST /api/buyers/snapshot-spend`), добова звірка (`POST /api/buyers/reconcile`), детальна карточка юзера з фільтрами по періоду (`GET /api/buyers/{id}?from=...&to=...`).
   - `/api/teams`: список команд і таблиць, додавання/редагування таблиці команди, синхронізація таблиці (`POST /api/teams/{id}/sync-sheet`), баланси рахунків FBM + команд.
   - `/api/reports`: категорії витрат (`GET/POST/DELETE /api/reports/categories`), витрати (`GET/POST/DELETE /api/reports/expenses`), зведений звіт прибутку/витрат + **Точка прибутку (Break-even)** + графік по днях (`GET /api/reports/summary?from=...&to=...&fee_percent=...`).
   - `/api/system`: статус версії Git та оновлення з GitHub (`GET /api/system/status`, `POST /api/system/update`).

---

## 3. Веб-інтерфейс (`apps/web`)

1. **Сторінка «Юзери та Команди» (`/buyers`) + Карточка Юзера (`/buyers/[id]`)**:
   - Верхній блок: Баланси кабінетів FBM (`Account1_US`, `Account1`) + Баланси команд із таблиць (з індикацією `< $1000` та мінусових балансів).
   - Вкладки/фільтр по командах, пошук, сортування (за пріоритетом, спендом сьогодні, загальним спендом, назвою, к-стю карток).
   - Галочка пріоритету (`★` / чекбокс) у рядку кожного юзера — піднімає пріоритетних юзерів наверх списку.
   - Кнопки: «Спарсити юзерів з FBM», «+ Додати юзера», «Зафіксувати спенд (3–4г)», «Звірка з FBM (24г)», керування Google-таблицями команд.
   - При кліку на юзера — **окрема карточка юзера** з вибором періоду (Сьогодні, 7 днів, Місяць, Довільні дати), графіком спенду по днях, списком його карток FBM і порівнянням з таблицею.
2. **Оновлення сторінки «Картки» (`/cards`)**:
   - Додано сортування по колонках: за юзером (баєром), за спендом, за назвою картки, за рахунком, за статусом.
   - Прив'язка картки до юзера дашборду з можливістю переходу в карточку юзера.
3. **Сторінка «Звітність» (`/reports`)**:
   - Калькулятор відсотка комісії, розрахунок Доходу, Витрат, Чистого прибутку.
   - Інтерактивний блок **«Точка прибутку (Break-even)»** з прогрес-баром та розрахунком необхідного спенду для покриття витрат.
   - Графік доходів і витрат по днях + розподіл витрат за категоріями.
   - Таблиця витрат з можливістю додавання витрат і створення власних категорій вручну.
4. **Обмежені права облікових записів (`/settings`)**:
   - При створенні та редагуванні користувача — вибір галочками дозволених розділів дашборду (`allowed_sections`).
   - Сайдбар автоматично показує лише дозволені розділи.
5. **Десктоп-додаток на ноутбук (`desktop/FB Rent.app`) + GitHub Auto-Update**:
   - Нативний macOS-додаток (`.app`), який відкриває дашборд в окремому десктоп-вікні, автоматично підтримує фонові сервіси живими та має кнопку «Оновити з GitHub» у UI.
