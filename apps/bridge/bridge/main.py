"""Bridge: тримає WebSocket до сервера, виконує команди в AdsPower Local API, повертає результат.
Запуск на машині з AdsPower:  python -m bridge.main"""
import asyncio
import json
import logging

import websockets

from bridge.adspower import AdsPower, AdsPowerError
from bridge.commands import execute
from bridge.config import Config

log = logging.getLogger("bridge")
HEARTBEAT = 20
MAX_BACKOFF = 60


async def handle(ws, ap: AdsPower, msg: dict) -> None:
    if msg.get("type") != "command":
        return
    cid = msg["id"]
    log.info("команда %s %s", msg["command"], msg.get("args"))
    # create_profile_full несе секрети в msg["profile"] (не логуємо їх)
    args = {**(msg.get("args") or {}), **(msg.get("profile") or {})}
    try:
        result = await execute(ap, msg["command"], args)
        reply = {"type": "result", "id": cid, "ok": True, "result": result}
    except (AdsPowerError, ValueError, KeyError) as e:
        log.warning("помилка команди %s: %s", cid, e)
        reply = {"type": "result", "id": cid, "ok": False, "error": str(e)}
    await ws.send(json.dumps(reply))


async def session(cfg: Config, ap: AdsPower) -> None:
    async with websockets.connect(cfg.server_ws_url, additional_headers={"Authorization": f"Bearer {cfg.token}"}) as ws:
        log.info("підключено до %s", cfg.server_ws_url)
        await ws.send(json.dumps({"type": "hello"}))

        async def heartbeat():
            while True:
                await asyncio.sleep(HEARTBEAT)
                await ws.send(json.dumps({"type": "hb"}))

        hb = asyncio.create_task(heartbeat())
        tasks: set[asyncio.Task] = set()
        try:
            async for raw in ws:  # команди виконуються по черзі завдяки локу в AdsPower-клієнті
                t = asyncio.create_task(handle(ws, ap, json.loads(raw)))
                tasks.add(t)
                t.add_done_callback(tasks.discard)
        finally:
            hb.cancel()
            for t in tasks:
                t.cancel()


async def run(cfg: Config) -> None:
    ap = AdsPower(cfg.adspower_url, cfg.adspower_key)
    backoff = 1
    try:
        while True:
            try:
                await session(cfg, ap)
                backoff = 1
            except (OSError, websockets.WebSocketException) as e:
                log.warning("зв'язок втрачено: %s; повтор через %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
    finally:
        await ap.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(Config.load()))


if __name__ == "__main__":
    main()
