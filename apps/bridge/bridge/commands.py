"""Виконавець команд із білого списку (ТЗ §6.2). Будь-що інше відхиляється."""
import re

from bridge.adspower import AdsPower

_FB_ID = re.compile(r"\b(\d{9,20})\b")


def _fb_user_id(p: dict) -> str | None:
    """FB ID профілю: з назви ('FB 615...'), з username, або з серійного — публічне, не секрет."""
    for src in (p.get("name"), p.get("username")):
        if src:
            m = _FB_ID.search(str(src))
            if m:
                return m.group(1)
    return None


def _profile_public(p: dict) -> dict:
    """Лише несекретні поля профілю AdsPower (без паролів/cookies/2FA). group_name є прямо у відповіді."""
    return {
        "profile_id": p.get("user_id"),
        "serial": p.get("serial_number"),
        "name": p.get("name"),
        "group_id": str(p.get("group_id")) if p.get("group_id") is not None else None,
        "group_name": p.get("group_name") or None,
        "username": p.get("username"),
        "domain": p.get("domain_name"),
        "country": p.get("ip_country"),
        "fb_user_id": _fb_user_id(p),
        "last_open_time": p.get("last_open_time"),
    }


async def execute(ap: AdsPower, command: str, args: dict) -> dict:
    if command == "list_profiles":
        rows = await ap.list_profiles()
        # Повертаємо ЛИШЕ несекретні поля (ТЗ §4): без password/fakey/cookie/proxy.
        return {"count": len(rows), "profiles": [_profile_public(p) for p in rows]}
    if command == "find_profile":
        p = await ap.find_profile(args["name"])
        return {"found": bool(p), "profile_id": p.get("user_id") if p else None}
    if command == "create_profile":
        # ідемпотентно: сервер міг повторно надіслати команду після обриву зв'язку
        existing = await ap.find_profile(args["name"])
        if existing:
            return {"profile_id": existing.get("user_id"), "already_exists": True}
        return {"profile_id": await ap.create_profile(args["name"], args.get("group")), "already_exists": False}
    if command == "create_profile_full":
        existing = await ap.find_profile(args["name"])
        if existing:
            return {"profile_id": existing.get("user_id"), "already_exists": True}
        pid = await ap.create_profile_full(
            args["name"], args.get("username", ""), args.get("password", ""), args.get("fakey", ""),
            args.get("cookie", ""), args.get("ua", ""), args.get("group"),
            remark=args.get("remark", ""), country=args.get("country", ""), proxy=args.get("proxy"),
        )
        return {"profile_id": pid, "already_exists": False}
    if command == "update_profile_group":
        await ap.update_group(args["profile_id"], args["group"])
        return {"profile_id": args["profile_id"], "group": args["group"]}
    if command == "open_profile":
        data = await ap.open_profile(args["profile_id"])
        return {"profile_id": args["profile_id"], "ws": (data.get("ws") or {}).get("puppeteer")}
    if command == "close_profile":
        await ap.close_profile(args["profile_id"])
        return {"profile_id": args["profile_id"]}
    raise ValueError(f"Команда не дозволена: {command}")
