"""Клієнт AdsPower Local API (v1). Лише те, що потрібне білому списку команд."""
import asyncio
import time

import httpx

MIN_INTERVAL = 1.1  # Local API обмежує ~1 запит/сек


class AdsPowerError(Exception):
    pass


class AdsPower:
    def __init__(self, base_url: str, api_key: str = "", transport: httpx.AsyncBaseTransport | None = None, min_interval: float = MIN_INTERVAL):
        # AdsPower Local API очікує ключ у заголовку Authorization: Bearer <key>
        # (підтверджено кодом офіц. CLI adspower-browser і емпірично: без нього "Require api-key",
        #  з невірним — "API Key mismatch").
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30, transport=transport)
        self._min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self):
        await self._http.aclose()

    async def _call(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
        async with self._lock:  # послідовно + пауза між запитами
            wait = self._last + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                r = await self._http.request(method, path, params=params, json=json)
            except httpx.HTTPError as e:
                raise AdsPowerError(f"AdsPower недоступний: {e}") from e
            finally:
                self._last = time.monotonic()
        try:
            body = r.json()
        except ValueError:
            raise AdsPowerError(f"Неочікувана відповідь AdsPower (HTTP {r.status_code})")
        if body.get("code") != 0:
            raise AdsPowerError(body.get("msg") or f"AdsPower code={body.get('code')}")
        return body.get("data") or {}

    async def list_profiles(self, page_size: int = 100, max_pages: int = 50) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            data = await self._call("GET", "/api/v1/user/list", params={"page": page, "page_size": page_size})
            rows = data.get("list") or []
            out += rows
            if len(rows) < page_size:
                break
        return out

    async def find_profile(self, name: str) -> dict | None:
        return next((p for p in await self.list_profiles() if p.get("name") == name), None)

    async def list_groups(self) -> list[dict]:
        data = await self._call("GET", "/api/v1/group/list", params={"page_size": 1000})
        return data.get("list") or []

    async def group_id(self, name: str, create: bool = True) -> str:
        data = await self._call("GET", "/api/v1/group/list", params={"page_size": 100})
        for g in data.get("list") or []:
            if g.get("group_name") == name:
                return str(g["group_id"])
        if not create:
            raise AdsPowerError(f"Група «{name}» не знайдена")
        created = await self._call("POST", "/api/v1/group/create", json={"group_name": name})
        return str(created["group_id"])

    async def create_profile(self, name: str, group: str | None = None) -> str:
        body = {"name": name, "group_id": await self.group_id(group) if group else "0", "user_proxy_config": {"proxy_soft": "no_proxy"}}
        data = await self._call("POST", "/api/v1/user/create", json=body)
        return str(data["id"])

    @staticmethod
    def _proxy_config(proxy: dict | None) -> dict:
        """proxy = {type, host, port, user?, password?} → user_proxy_config AdsPower. Порожньо → no_proxy."""
        if not proxy or not proxy.get("host"):
            return {"proxy_soft": "no_proxy"}
        cfg = {
            "proxy_soft": "other",
            "proxy_type": (proxy.get("type") or "http"),
            "proxy_host": str(proxy["host"]),
            "proxy_port": str(proxy.get("port") or ""),
        }
        if proxy.get("user"):
            cfg["proxy_user"] = proxy["user"]
        if proxy.get("password"):
            cfg["proxy_password"] = proxy["password"]
        return cfg

    async def create_profile_full(self, name: str, username: str, password: str, fakey: str,
                                  cookie: str, ua: str, group: str | None = None,
                                  remark: str = "", country: str = "", proxy: dict | None = None) -> str:
        """Профіль AdsPower з готовими даними FB (куплений акаунт із cookies).

        Поля за офіційним skill adspower-browser (references/browser-profile-management.md):
        top-level platform/cookie/username/password/fakey/remark/country, UA в fingerprint_config.ua.
        Секрети приходять лише по WS, на диску bridge не зберігаються.
        """
        body = {
            "name": name,
            "group_id": await self.group_id(group) if group else "0",
            "domain_name": "facebook.com",  # при username/password AdsPower вимагає саме domain_name (перевірено емпірично)
            "username": username,
            "password": password,
            "fakey": fakey,
            "cookie": cookie,
            "ignore_cookie_error": "1",  # куплені акаунти — cookies можуть не пройти строгу перевірку
            "user_proxy_config": self._proxy_config(proxy),
            "fingerprint_config": {"ua": ua} if ua else {"random_ua": {"ua_system_version": []}},
        }
        if remark:
            body["remark"] = remark[:1500]
        if country:
            body["country"] = country.lower()[:2]
        data = await self._call("POST", "/api/v1/user/create", json=body)
        return str(data["id"])

    async def update_group(self, profile_id: str, group: str) -> None:
        # перенос у групу — саме /user/regroup; /user/update group_id повертає success, але НЕ переносить
        gid = await self.group_id(group)
        await self._call("POST", "/api/v1/user/regroup", json={"group_id": gid, "user_ids": [profile_id]})

    async def open_profile(self, profile_id: str) -> dict:
        return await self._call("GET", "/api/v1/browser/start", params={"user_id": profile_id})

    async def close_profile(self, profile_id: str) -> None:
        await self._call("GET", "/api/v1/browser/stop", params={"user_id": profile_id})
