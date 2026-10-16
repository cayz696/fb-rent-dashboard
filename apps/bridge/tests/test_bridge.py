import json

import httpx
import pytest

from bridge.adspower import AdsPower, AdsPowerError
from bridge.commands import execute
from bridge.main import handle


class FakeAdsPower:
    """Імітація Local API: профілі й групи в пам'яті."""

    def __init__(self):
        self.profiles = [{"user_id": "k1", "name": "FB-0001", "group_id": "0"}]
        self.groups = [{"group_id": "5", "group_name": "Ready"}]
        self.calls: list[tuple[str, str]] = []
        self.fail_next = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, q = req.url.path, dict(req.url.params)
        body = json.loads(req.content) if req.content else {}
        self.calls.append((req.method, path))
        ok = lambda data=None: httpx.Response(200, json={"code": 0, "msg": "success", "data": data or {}})
        if self.fail_next:
            self.fail_next = False
            return httpx.Response(200, json={"code": -1, "msg": "Too many request per second"})
        if path == "/api/v1/user/list":
            return ok({"list": self.profiles, "page": int(q["page"]), "page_size": int(q["page_size"])} if int(q["page"]) == 1 else {"list": []})
        if path == "/api/v1/group/list":
            return ok({"list": self.groups})
        if path == "/api/v1/group/create":
            g = {"group_id": str(len(self.groups) + 5), "group_name": body["group_name"]}
            self.groups.append(g)
            return ok(g)
        if path == "/api/v1/user/create":
            pid = f"k{len(self.profiles) + 1}"
            self.profiles.append({"user_id": pid, "name": body["name"], "group_id": body["group_id"]})
            return ok({"id": pid})
        if path == "/api/v1/user/regroup":
            for uid in body["user_ids"]:
                next(p for p in self.profiles if p["user_id"] == uid)["group_id"] = body["group_id"]
            return ok()
        if path == "/api/v1/browser/start":
            return ok({"ws": {"puppeteer": f"ws://127.0.0.1:9222/{q['user_id']}"}})
        if path == "/api/v1/browser/stop":
            return ok()
        return httpx.Response(404, json={})


@pytest.fixture
def fake():
    return FakeAdsPower()


@pytest.fixture
def ap(fake):
    return AdsPower("http://adspower.test", "key", transport=httpx.MockTransport(fake), min_interval=0)


async def test_create_profile_and_idempotency(ap, fake):
    r = await execute(ap, "create_profile", {"name": "FB-0002"})
    assert r == {"profile_id": "k2", "already_exists": False}
    again = await execute(ap, "create_profile", {"name": "FB-0002"})  # повторна доставка команди
    assert again == {"profile_id": "k2", "already_exists": True}
    assert len([p for p in fake.profiles if p["name"] == "FB-0002"]) == 1


async def test_find_list_open_close(ap):
    assert await execute(ap, "find_profile", {"name": "FB-0001"}) == {"found": True, "profile_id": "k1"}
    assert (await execute(ap, "find_profile", {"name": "nope"}))["found"] is False
    assert (await execute(ap, "list_profiles", {}))["count"] == 1
    assert (await execute(ap, "open_profile", {"profile_id": "k1"}))["ws"].endswith("/k1")
    assert await execute(ap, "close_profile", {"profile_id": "k1"}) == {"profile_id": "k1"}


async def test_update_group_creates_missing(ap, fake):
    await execute(ap, "update_profile_group", {"profile_id": "k1", "group": "Ready"})
    assert fake.profiles[0]["group_id"] == "5"
    await execute(ap, "update_profile_group", {"profile_id": "k1", "group": "Issued"})
    assert fake.profiles[0]["group_id"] == "6"


async def test_non_whitelisted_command_rejected(ap, fake):
    with pytest.raises(ValueError):
        await execute(ap, "delete_profile", {"profile_id": "k1"})
    assert fake.calls == []


async def test_adspower_error_propagates(ap, fake):
    fake.fail_next = True
    with pytest.raises(AdsPowerError, match="Too many"):
        await execute(ap, "list_profiles", {})


async def test_api_key_sent_as_bearer_header(fake):
    seen = {}
    def spy(req):
        seen["auth"] = req.headers.get("authorization")
        return fake(req)
    ap = AdsPower("http://x", "secret", transport=httpx.MockTransport(spy), min_interval=0)
    await ap.list_profiles()
    assert seen["auth"] == "Bearer secret"  # AdsPower Local API: Authorization: Bearer <key>


class FakeWS:
    def __init__(self): self.sent = []
    async def send(self, data): self.sent.append(json.loads(data))


async def test_handle_success_and_error_replies(ap, fake):
    ws = FakeWS()
    await handle(ws, ap, {"type": "command", "id": "c1", "command": "create_profile", "args": {"name": "FB-0009"}})
    fake.fail_next = True
    await handle(ws, ap, {"type": "command", "id": "c2", "command": "list_profiles", "args": {}})
    await handle(ws, ap, {"type": "command", "id": "c3", "command": "rm_rf", "args": {}})
    await handle(ws, ap, {"type": "hello"})  # ігнорується
    ok, err, bad = ws.sent
    assert ok == {"type": "result", "id": "c1", "ok": True, "result": {"profile_id": "k2", "already_exists": False}}
    assert err["ok"] is False and "Too many" in err["error"]
    assert bad["ok"] is False and "не дозволена" in bad["error"]


async def test_create_profile_full_sends_cookies_and_2fa(ap, fake):
    r = await execute(ap, "create_profile_full", {
        "name": "FB-0055", "username": "u@e.com", "password": "pw", "fakey": "SECRET32",
        "cookie": '[{"name":"c_user","value":"615"}]', "ua": "Mozilla/5.0 test",
    })
    assert r["profile_id"] == "k2" and r["already_exists"] is False
    # профіль реально створився у фейковому AdsPower
    assert any(p["name"] == "FB-0055" for p in fake.profiles)


async def test_create_profile_full_idempotent(ap):
    first = await execute(ap, "create_profile_full", {"name": "FB-0001", "username": "u", "password": "p", "fakey": "", "cookie": "[]", "ua": ""})
    assert first["already_exists"] is True and first["profile_id"] == "k1"  # FB-0001 уже є у фейку


async def test_create_profile_full_with_proxy(ap, fake):
    captured = {}
    orig = fake.__call__
    def spy(req):
        import json as j
        if req.url.path == "/api/v1/user/create":
            captured["body"] = j.loads(req.content)
        return orig(req)
    ap2 = AdsPower("http://x", "k", transport=httpx.MockTransport(spy), min_interval=0)
    # підкладемо профілі spy-клієнту (find_profile ходить у list)
    await execute(ap2, "create_profile_full", {
        "name": "FB-0100", "username": "u", "password": "p", "fakey": "", "cookie": "[]", "ua": "UA",
        "proxy": {"type": "socks5", "host": "1.2.3.4", "port": "1080", "user": "pu", "password": "pp"},
    })
    cfg = captured["body"]["user_proxy_config"]
    assert cfg == {"proxy_soft": "other", "proxy_type": "socks5", "proxy_host": "1.2.3.4", "proxy_port": "1080", "proxy_user": "pu", "proxy_password": "pp"}


def test_proxy_config_empty():
    from bridge.adspower import AdsPower as AP
    assert AP._proxy_config(None) == {"proxy_soft": "no_proxy"}
    assert AP._proxy_config({"host": ""}) == {"proxy_soft": "no_proxy"}
