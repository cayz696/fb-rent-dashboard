from __future__ import annotations
"""Парсер замовлення зі стоку (order_*.txt) → профіль AdsPower. Детерміновано, без LLM.

Замінює ручний крок «прогнати order.txt через ChatGPT» (див. docs/process-analysis.md, крок 4).

Формат входу — рядок на акаунт, поля через TAB (15 полів):
  0 ім'я | 1 логін FB (пошта) | 2 пароль FB | 3 пошта | 4 пароль пошти | 5 дата народж. |
  6 FB ID | 7 User-Agent | 8 лінк FB | 9 токен | 10 cookies(JSON) | 11 Google Drive |
  12 країна | 13 2FA-лінк | 14 резервні коди

Формат виходу — блок key=value на профіль (AdsPower mass import), блоки розділені порожнім рядком.

Секрети (паролі, cookies, токен, 2FA, резервні коди) в нашій БД НЕ зберігаються (ТЗ §4):
`AccountFields` містить лише несекретні поля; повний профіль живе тільки в згенерованому файлі.
"""
import json
import re
from dataclasses import dataclass, field

FIELDS = 15


class OrderParseError(Exception):
    pass


@dataclass
class ParsedAccount:
    # для AdsPower-файлу (містить секрети — тільки в пам'яті / у файлі, не в БД)
    name: str
    fb_login: str
    fb_password: str
    email: str
    email_password: str
    birthday: str
    fb_user_id: str
    user_agent: str
    fb_link: str
    token: str
    cookies_raw: str
    gdrive: str
    country: str
    twofa_url: str
    backup_codes: str
    twofa_secret: str = ""
    warnings: list[str] = field(default_factory=list)

    # ---- лише несекретні поля для нашої БД (ТЗ §4)
    def db_fields(self) -> dict:
        return {
            "fb_user_id": self.fb_user_id or None,
            "fb_login": self.fb_login or None,
            "fb_link": self.fb_link or None,
            "country": self.country or None,
        }


def _secret_from_2fa(url: str) -> str:
    """https://2fa.fb.tools/<SECRET> → <SECRET> (Base32). Порожньо, якщо не схоже на секрет."""
    if not url:
        return ""
    last = url.rstrip("/").rsplit("/", 1)[-1].strip()
    return last if re.fullmatch(r"[A-Z2-7]{16,64}", last) else ""


def parse_line(line: str, idx: int) -> ParsedAccount | None:
    if not line.strip():
        return None
    cols = line.rstrip("\n").split("\t")
    if len(cols) < FIELDS:
        raise OrderParseError(f"Рядок {idx}: очікувалось {FIELDS} полів через TAB, отримано {len(cols)}")
    c = [x.strip() for x in cols[:FIELDS]]
    acc = ParsedAccount(
        name=c[0], fb_login=c[1], fb_password=c[2], email=c[3], email_password=c[4], birthday=c[5],
        fb_user_id=c[6], user_agent=c[7], fb_link=c[8], token=c[9], cookies_raw=c[10], gdrive=c[11],
        country=c[12], twofa_url=c[13], backup_codes=c[14],
    )
    acc.twofa_secret = _secret_from_2fa(acc.twofa_url)
    # валідація критичного, без падіння всього імпорту — збираємо попередження
    if not re.fullmatch(r"\d{5,20}", acc.fb_user_id):
        acc.warnings.append("FB ID не схожий на число")
    try:
        cookies = json.loads(acc.cookies_raw)
        if not any(k.get("name") == "c_user" and k.get("value") == acc.fb_user_id for k in cookies):
            acc.warnings.append("c_user у cookies не збігається з FB ID")
    except (json.JSONDecodeError, TypeError):
        acc.warnings.append("cookies не є валідним JSON")
    if not acc.twofa_secret and acc.twofa_url:
        acc.warnings.append("не вдалося витягти 2FA-секрет із лінка")
    return acc


def parse_order(text: str) -> list[ParsedAccount]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        acc = parse_line(line, i)
        if acc:
            out.append(acc)
    if not out:
        raise OrderParseError("У файлі не знайдено жодного акаунта")
    return out


def _remark(a: ParsedAccount) -> str:
    return " | ".join([
        f"Имя: {a.name}", f"Логин Facebook: {a.fb_login}", f"Пароль Facebook: {a.fb_password}",
        f"Почта: {a.email}", f"Пароль почты: {a.email_password}", f"Дата рождения: {a.birthday}",
        f"Facebook ID: {a.fb_user_id}", f"User-Agent: {a.user_agent}", f"Ссылка Facebook: {a.fb_link}",
        f"Токен (исходное поле 10): {a.token}", f"Ссылка Google Drive: {a.gdrive}",
        f"Страна (исходное поле 13): {a.country}", f"Ссылка 2FA: {a.twofa_url}",
        f"Резервные коды: {a.backup_codes}",
    ])


def account_remark(a: ParsedAccount) -> str:
    """Публічний доступ до рядка нотаток (той самий, що в AdsPower-файлі). Містить паролі — як секрет."""
    return _remark(a)


def to_adspower_block(a: ParsedAccount) -> str:
    lines = [
        f"name={a.name}",
        f"remark={_remark(a)}",
        "platform=facebook.com",
        f"username={a.fb_login}",
        f"password={a.fb_password}",
        f"fakey={a.twofa_secret}",
        f"cookie={a.cookies_raw}",
        "proxytype=noproxy",
        f"ua={a.user_agent}",
    ]
    return "\n".join(lines)


def to_adspower_file(accounts: list[ParsedAccount]) -> str:
    """Повний файл для масового імпорту AdsPower (блоки розділені порожнім рядком, як у зразку)."""
    return "\n\n".join(to_adspower_block(a) for a in accounts) + "\n"
