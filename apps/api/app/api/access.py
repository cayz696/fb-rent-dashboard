"""Доступ до розділів. Той самий сенс, що hasSectionAccess на вебі: список allowed_sections
обов’язковий, якщо він заданий; інакше не-адмін не бачить фінанси, звітність і налаштування."""
from __future__ import annotations

from dataclasses import dataclass

from app.models import Role, User

RESTRICTED_BY_DEFAULT = frozenset({"settings", "finance", "reports"})


def has_section(user: User, section: str) -> bool:
    sections = user.allowed_sections or []
    if user.role == Role.admin and not sections:
        return True
    if sections:
        return section in sections
    return section not in RESTRICTED_BY_DEFAULT


@dataclass(frozen=True)
class AccessRule:
    """public — без сесії; auth — будь-який активний користувач; section — хоча б один розділ;
    writer_section — розділ і роль admin/operator."""

    kind: str
    sections: tuple[str, ...] = ()


def access_rule(path: str) -> AccessRule:
    if (
        path in ("/api/health", "/api/auth/login", "/api/auth/2fa/setup", "/api/auth/2fa/verify", "/api/clover/spend", "/api/bridge/ws")
        or path.startswith("/api/docs")
        or path.startswith("/api/openapi")
        or path.startswith("/api/redoc")
    ):
        return AccessRule("public")
    if path in ("/api/me", "/api/auth/logout", "/api/notifications", "/api/bridge/status"):
        return AccessRule("auth")
    if path.startswith("/api/fbm/cards/") and path.endswith("/codes"):
        return AccessRule("writer_section", ("cards",))
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("/api/reports", ("reports",)),
        ("/api/finance", ("finance",)),
        ("/api/users", ("settings",)),
        ("/api/system", ("settings",)),
        ("/api/clover", ("settings",)),
        ("/api/buyers", ("buyers",)),
        ("/api/fbm", ("cards",)),
        ("/api/adspower", ("adspower",)),
        ("/api/import", ("import",)),
        ("/api/dashboard", ("dashboard",)),
        ("/api/signals", ("dashboard", "accounts")),
        ("/api/requests", ("requests", "dashboard")),
        ("/api/events", ("events", "accounts")),
        ("/api/accounts", ("accounts", "kanban", "dashboard", "requests")),
        ("/api/clients", ("clients", "accounts", "requests", "kanban")),
        ("/api/suppliers", ("suppliers", "accounts", "import")),
        ("/api/batches", ("suppliers", "accounts", "import")),
        ("/api/bridge", ("accounts", "adspower", "settings", "import")),
    )
    for prefix, sections in rules:
        if path == prefix or path.startswith(prefix + "/"):
            return AccessRule("section", sections)
    return AccessRule("public")
