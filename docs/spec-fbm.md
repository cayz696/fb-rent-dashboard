# Інтеграція FBM-pay (картки, спенд, 3DS)

Офіційний API замість розширення. Ключ і доки отримано (05.10.2026+).

## API
- База: `https://fbm-pay.com`, авторизація — заголовок **`X-API-Key`**.
- Ключ, схоже, **read-only (аналітика)** — нам і треба лише GET.
- Ендпоінти (GET): `cards`, `cards/{id}`, `cards/{id}/codes/{type}` (3DS), `cards/{id}/history`, `cards/banks|bins`, `payments` (спенд!), `accounts` (счета) + `accounts/transactions`, `users` (баери). POST `cards` (випуск) — не використовуємо.

## Поля (з прикладів доки)
- **card**: `cardId`, `name`, `cardMask` («446253******2570» → last4=2570), `paymentSystem`, `statusName`, `stateName`, `balance`, `currency`, `account{iban,name,balance}`, `usersCount`.
- **payment** (транзакція): `ID`, `cardId`, `cardNumber`(маска), `accountIban`, `dateTime`, `status`, `type` (Credit/Debit), `merchantAmount`, `accountAmount`, `balance`, `currency`, `details`. → **Debit = спенд на рекламу.**
- **code** (3DS): `cardId`, `code` («82366»), `description` (містить OTP), `type` («3DS»), `createdAt`, `user`.
- **user**: `id`, `name`, `email`, `telegram`, `role`, `blocked`, `accounts[]`. → баери (VSamurai…).
- **account** (счет): `iban`, `name`, `balance`, `availableAmount`, `status`.

## Зв'язок із нашими акаунтами
- Наш `accounts.card_last4` ↔ `card.cardMask` останні 4. Так картка FBM чіпляється до FB-акаунта.
- Спенд по картці (payments, type=Debit) → ще одне джерело спенду поряд з Clover/аналітичним API.
- 3DS-коди картки → показуємо в UI (щоб не лазити у FBM).

## §4 (безпека)
- `cardMask` — маскована, зберігати можна (ми й так тримаємо лише last4).
- `cards/{id}/credentials` (повний PAN) — **НЕ викликаємо, не зберігаємо.**
- 3DS-коди — транзитні (показ, не довге зберігання).

## План реалізації
1. Клієнт `integrations/fbm.py` (httpx, X-API-Key) + мапери (last4, спенд із payments, код із 3DS). **Юніт-тести на прикладах доки — без живих викликів.**
2. Конфіг `FBM_API_KEY`, `FBM_API_URL`.
3. Модель: `fbm_cards` (снепшот карток) + спенд по картках (payments) як джерело; зв'язок з акаунтом по last4.
4. Ендпоінти `/api/fbm/*` (картки, коди, статус) + розділ «Картки» в UI; у картці акаунта — баланс/ліміт/3DS його картки.
5. Сигнал «ліміт картки майже вичерпано».

## Суміжне (з розмови)
- **`clients.bm_id`** — вести BM ID по кожному клієнту (для «Розшарити доступ»). ✅ додаємо.
- **Дані в AdsPower-профілі** (токен/BM/кабінет у remark) — витягти й перевірити; для share-access Фаза 2 bridge читатиме токен звідти.
