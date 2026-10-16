# FB Rent bridge

Агент на машині з AdsPower. Сам підключається до сервера по WebSocket (`Authorization: Bearer <BRIDGE_TOKEN>`),
забирає команди з черги й виконує їх в AdsPower Local API. Сервер ніколи не звертається до цієї машини напряму.

Дозволені команди (білий список): `list_profiles`, `create_profile`, `update_profile_group`, `open_profile`, `close_profile`, `find_profile`.
`create_profile` ідемпотентний: перед створенням шукає профіль з таким самим ім'ям (код `FB-XXXX`).

## Запуск
```bash
cd apps/bridge
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# змінні (з .env поряд або з середовища):
#   BRIDGE_SERVER_WS_URL=wss://<сервер>/api/bridge/ws   (dev: ws://localhost:8010/api/bridge/ws)
#   BRIDGE_TOKEN=<той самий, що в .env сервера>
#   ADSPOWER_API_URL=http://local.adspower.net:50325
#   ADSPOWER_API_KEY=<ключ Local API, лишається лише на цій машині>
.venv/bin/python -m bridge.main
```
Обрив зв'язку → автоперепідключення (1→60 с). Команди, надіслані без відповіді, сервер повертає в чергу.
Тести: `.venv/bin/python -m pytest` (AdsPower імітується).
