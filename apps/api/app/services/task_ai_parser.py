from __future__ import annotations
"""ШІ-двигун аналізу контексту повідомлень із Telegram-груп та генерації задач для команди.

Підтримує двошарову архітектуру:
1. LLM-аналізатор (OpenAI / Gemini / сумісний API) з урахуванням історії чату (thread context),
   списку баєрів, команд, клієнтів та карток FBM.
2. Вбудований доменний NLP-аналізатор арбітражного контексту (FB Ads, FBM Cards, AdsPower, БМ, чеки, білінг),
   який працює миттєво навіть без зовнішнього API-ключа або як fallback.
"""
import json
import re
import uuid
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Buyer, Client, SystemState, Team

AI_CONFIG_KEY = "tasks_ai_config"

DEFAULT_SYSTEM_PROMPT = (
    "Ти — розумний ШІ-диспетчер арбітражної та фарм-команди Skull Partners (FB Rent & Media Buying). "
    "Твоє завдання — читати повідомлення з робочих Telegram-груп (баєри, клієнти, фармери, техспеціалісти), "
    "розуміти контекст діалогу та визначати, чи містить повідомлення задачу/заявку для команди.\n"
    "Категорії задач:\n"
    "- issue_accounts: запит на видачу FB-акаунтів (кількість, ГЕО, ліміт, БМ)\n"
    "- card_issue: проблеми з картками FBM (деклайн, ліміт, заміна картки, поповнення балансу, білінг)\n"
    "- bm_share: розшарка БМ, передача пікселя, лінковка кабінетів, доступи\n"
    "- account_check: чекпоінт, селфі, ЗРД, бан, проксі, AdsPower, 2FA код\n"
    "- procurement: закупівля розхідників, акаунтів, проксі, фарм\n"
    "- finance: звірка спенду, баланс таблиці, оплата USDT, комісія\n"
    "- general: інші робочі доручення\n"
    "- noise: звичайне спілкування без задачі ('ок', 'дякую', '+', привітання)"
)


def get_ai_config(db: Session) -> Dict[str, Any]:
    row = db.get(SystemState, AI_CONFIG_KEY)
    val = dict(row.value) if row and row.value else {}
    return {
        "provider": val.get("provider", "hybrid"),  # hybrid | openai | gemini | domain_nlp
        "model": val.get("model", "gpt-4o-mini"),
        "api_key": val.get("api_key", ""),
        "api_key_masked": ("••••" + val["api_key"][-4:]) if val.get("api_key") and len(val.get("api_key", "")) > 6 else "",
        "has_api_key": bool(val.get("api_key")),
        "confidence_threshold": int(val.get("confidence_threshold", 60)),
        "ignore_short_noise": bool(val.get("ignore_short_noise", True)),
        "auto_assign_by_category": bool(val.get("auto_assign_by_category", True)),
        "system_prompt": val.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
    }


def save_ai_config(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = db.get(SystemState, AI_CONFIG_KEY)
    current = dict(row.value) if row and row.value else {}
    for k in ("provider", "model", "confidence_threshold", "ignore_short_noise", "auto_assign_by_category", "system_prompt"):
        if k in payload and payload[k] is not None:
            current[k] = payload[k]
    if "api_key" in payload and payload["api_key"] is not None:
        raw_key = str(payload["api_key"]).strip()
        if raw_key and not raw_key.startswith("••••"):
            current["api_key"] = raw_key
        elif raw_key == "":
            current["api_key"] = ""

    if not row:
        row = SystemState(key=AI_CONFIG_KEY, value=current)
        db.add(row)
    else:
        row.value = current
    db.commit()
    return get_ai_config(db)


# ─────────────────────────────────────────────────────────────────────────────
# Доменний контекст-різолвер (Баєри, Команди, Клієнти, Картки, Акаунти)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_db_entities(
    db: Session,
    text: str,
    sender_username: Optional[str] = None,
    sender_name: Optional[str] = None,
    group_team_id: Optional[uuid.UUID] = None,
    group_client_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """Знаходить згадки баєрів, команд, клієнтів, кодів акаунтів (FB-XXXX) та карток (••XXXX) у тексті."""
    combined = f"{text or ''} {sender_username or ''} {sender_name or ''}".lower()

    # 1. Коди акаунтів FB-0001
    account_codes = list(dict.fromkeys(re.findall(r"\bfb-\d{3,6}\b", text or "", flags=re.IGNORECASE)))
    account_codes = [c.upper() for c in account_codes]

    # 2. Останні 4 цифри картки (••9443, *9443, карта 9443)
    card_matches = re.findall(r"(?:••|\*\*|\*|карт[аиуеою]\s*#?\s*|card\s*#?\s*)(\d{4})\b", text or "", flags=re.IGNORECASE)
    card_last4 = list(dict.fromkeys(card_matches))

    # 3. BM ID (12–17 цифр)
    bm_matches = re.findall(r"\b(\d{13,17})\b", text or "")
    bm_id = bm_matches[0] if bm_matches else None

    # 4. Пошук баєра (ігноруємо короткі/числові назви типу '1', шукаємо по межах слів, спочатку довші імена)
    matched_buyer: Optional[Buyer] = None
    buyers = sorted(db.scalars(select(Buyer)).all(), key=lambda x: len(x.name or ""), reverse=True)
    for b in buyers:
        b_lower = (b.name or "").strip().lower()
        if len(b_lower) < 3 or b_lower.isdigit():
            continue
        if re.search(rf"(?<![a-zа-яіїєґ0-9]){re.escape(b_lower)}(?![a-zа-яіїєґ0-9])", combined):
            matched_buyer = b
            break
    # Якщо баєра не знайдено прямо, але є card_last4 — перевіряємо кеш FBM карток
    if not matched_buyer and card_last4:
        fbm_cache = db.get(SystemState, "fbm_cards_cache")
        if fbm_cache and fbm_cache.value:
            for c in fbm_cache.value.get("cards", []):
                if c.get("last4") in card_last4 and c.get("name"):
                    cname_low = str(c["name"]).lower()
                    for b in buyers:
                        b_lower = (b.name or "").strip().lower()
                        if len(b_lower) >= 3 and not b_lower.isdigit() and b_lower in cname_low:
                            matched_buyer = b
                            break
                if matched_buyer:
                    break

    # 5. Пошук команди
    matched_team_id: Optional[uuid.UUID] = group_team_id or (matched_buyer.team_id if matched_buyer else None)
    matched_team_name: Optional[str] = None
    teams = {t.id: t for t in db.scalars(select(Team)).all()}
    if not matched_team_id:
        for t in teams.values():
            if t.name.lower() in combined:
                matched_team_id = t.id
                break
    if matched_team_id and matched_team_id in teams:
        matched_team_name = teams[matched_team_id].name

    # 6. Пошук клієнта
    matched_client_id: Optional[uuid.UUID] = group_client_id
    matched_client_name: Optional[str] = None
    clients = db.scalars(select(Client)).all()
    if not matched_client_id:
        clean_uname = (sender_username or "").lstrip("@").lower()
        for cl in clients:
            if cl.name.lower() in combined:
                matched_client_id = cl.id
                matched_client_name = cl.name
                break
            if clean_uname and any(u.lstrip("@").lower() == clean_uname for u in (cl.telegram_usernames or [])):
                matched_client_id = cl.id
                matched_client_name = cl.name
                break
    else:
        for cl in clients:
            if cl.id == matched_client_id:
                matched_client_name = cl.name
                break

    return {
        "account_codes": account_codes,
        "card_last4": card_last4,
        "bm_id": bm_id,
        "buyer_id": str(matched_buyer.id) if matched_buyer else None,
        "buyer_name": matched_buyer.name if matched_buyer else None,
        "team_id": str(matched_team_id) if matched_team_id else None,
        "team_name": matched_team_name,
        "client_id": str(matched_client_id) if matched_client_id else None,
        "client_name": matched_client_name,
    }


def _extract_qty_geo_limit(text: str) -> Dict[str, Any]:
    """Витягує кількість акаунтів, ГЕО та ліміт із тексту заявки."""
    low = text.lower()
    # Кількість (напр. "5 аків", "10 шт", "нужно 3 фб", "видай 2 кабінети")
    qty = None
    qty_m = re.search(
        r"(?:дай(?:те)?|нужн[оы]|треба|видай(?:те)?|запрос\s+на|прошу|візьму|го)\s+(\d{1,3})\b"
        r"|\b(\d{1,3})\s*(?:ак(?:ків|ів|ка|ків|а|и|ов)?|шт|каб(?:ів|інетів|и)?|фб|fb|профіл[яів])",
        low,
    )
    if qty_m:
        val = int(qty_m.group(1) or qty_m.group(2))
        if 1 <= val <= 200:
            qty = val

    # ГЕО
    geo_map = {
        "US": ["сша", "usa", "us", "америк"],
        "UA": ["укр", "ua", "ukraine"],
        "PL": ["пол", "pl", "poland", "польщ", "польш"],
        "DE": ["нім", "герм", "de", "germany"],
        "GB": ["брит", "uk", "gb", "англі"],
        "BR": ["браз", "br", "brazil"],
        "KZ": ["казах", "kz"],
        "ES": ["іспан", "испан", "es", "spain"],
        "IT": ["італ", "итал", "it", "italy"],
        "FR": ["франц", "fr", "france"],
        "TIER1": ["тір1", "тир1", "tier-1", "tier1", "європ", "европ", "eu"],
    }
    detected_geo = None
    for code, kws in geo_map.items():
        for kw in kws:
            if re.search(rf"\b{kw}", low):
                detected_geo = code
                break
        if detected_geo:
            break

    # Ліміт (напр. "ліміт 250", "лім 50$", "250$", "nolimit", "безлім")
    limit = None
    if any(w in low for w in ("безлім", "безлим", "nolimit", "no limit", "анлім")):
        limit = "nolimit"
    else:
        lim_m = re.search(r"(?:лім(?:іт|ит)?|limit)\s*[:=]?\s*(\d{2,4})|\b(50|250|1500)\s*\$", low)
        if lim_m:
            limit = lim_m.group(1) or lim_m.group(2)

    return {"qty": qty, "geo": detected_geo, "limit": limit}


def _build_checklist(category: str, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
    buyer_label = f" ({entities['buyer_name']})" if entities.get("buyer_name") else ""
    cards_label = f" ••{', ••'.join(entities['card_last4'])}" if entities.get("card_last4") else ""
    accs_label = f" {', '.join(entities['account_codes'])}" if entities.get("account_codes") else ""

    templates = {
        "issue_accounts": [
            f"Перевірити пул готових акаунтів ( потрібно: {entities.get('qty') or 1} шт{', ГЕО ' + entities['geo'] if entities.get('geo') else ''} )",
            "Прив'язати платіжну картку FBM та перевірити ліміт спенду",
            f"Розшарити кабінети на БМ клієнта{(' ' + entities['bm_id']) if entities.get('bm_id') else ''}",
            "Перевести акаунти в статус «Виданий» та відписати в Telegram-групу",
        ],
        "card_issue": [
            f"Перевірити картку{cards_label}{buyer_label} у кабінеті FBM Cards",
            "Перевірити баланс субакаунта та останні Declined-транзакції",
            "Замінити або перепідв'язати картку в AdsPower / FB білінгу",
            "Підтвердити успішне списання в робочому чаті",
        ],
        "bm_share": [
            f"Перевірити ID Business Manager / Пікселя{(' (' + entities['bm_id'] + ')') if entities.get('bm_id') else ''}",
            f"Відкрити профіль{accs_label} в AdsPower та надати партнерський доступ",
            "Перевірити, що баєр/клієнт прийняв доступ без помилок",
        ],
        "account_check": [
            f"Відкрити профіль{accs_label}{buyer_label} у AdsPower та перевірити проксі",
            "Витягнути 2FA / код підтвердження або завантажити селфі на чекпоінт",
            "Оновити статус акаунта на Канбан-дошці",
            "Повідомити баєра про відновлення роботи",
        ],
        "procurement": [
            "Узгодити кількість та ГЕО розхідників із постачальником",
            "Завантажити пачку через розділ «Імпорт замовлення»",
            "Запустити первинний прогрів у AdsPower",
        ],
        "finance": [
            f"Звірити фактичний спенд по FBM API{buyer_label}",
            "Синхронізувати дані з Google Таблицею команди",
            "Підтвердити актуальний баланс у чаті",
        ],
        "general": [
            "Уточнити деталі запиту в робочій групі",
            "Виконати задачу та зафіксувати результат",
        ],
    }
    steps = templates.get(category, templates["general"])
    return [{"id": f"chk-{i+1}", "text": s, "done": False} for i, s in enumerate(steps)]


# ─────────────────────────────────────────────────────────────────────────────
# Доменний NLP-класифікатор + LLM виклик
# ─────────────────────────────────────────────────────────────────────────────

NOISE_PATTERNS = re.compile(
    r"^\s*(?:ок|окей|ok|okay|дякую|спасибо|спс|thx|привіт|привет|доброго\s+ранку|добрий\s+день|"
    r"прийнято|принял|понял|зрозумів|\++|👍+|🔥+|👌+|так|да|ні|нет|го|супер|чітко|четко)\s*[!.,)]*\s*$",
    flags=re.IGNORECASE,
)


def _domain_heuristic_analyze(
    raw_text: str,
    context_messages: List[str],
    entities: Dict[str, Any],
    sender_label: str,
    chat_title: str,
) -> Dict[str, Any]:
    clean = (raw_text or "").strip()
    full_context_text = "\n".join([*context_messages, clean]).strip()
    low = clean.lower()
    ctx_low = full_context_text.lower()

    # Якщо коротке повідомлення типу "ок", "дякую", "+"
    if len(clean) < 3 or NOISE_PATTERNS.match(clean):
        return {
            "is_actionable": False,
            "category": "noise",
            "priority": "low",
            "confidence": 95,
            "title": "Повідомлення без задачі (чат)",
            "description": "Коротке підтвердження або вітання, не потребує створення задачі.",
            "reasoning": "Відфільтровано як звичайне повідомлення чату.",
            "suggested_reply": None,
            "entities": entities,
            "checklist": [],
        }

    # Доповнюємо сутності з урахуванням попередніх повідомлень треду
    qgl = _extract_qty_geo_limit(full_context_text)
    entities = {**entities, **{k: v for k, v in qgl.items() if v is not None}}

    # Визначення категорії за ваговими маркерами
    scores = {
        "issue_accounts": 0,
        "card_issue": 0,
        "bm_share": 0,
        "account_check": 0,
        "procurement": 0,
        "finance": 0,
        "general": 0,
    }

    # 1. Видача акаунтів
    if any(w in ctx_low for w in ("дай ", "дайте", "видай", "видайте", "нужно ", "нужны ", "треба ", "запрос на", "запит на", "підготуй", "насип")):
        if any(w in ctx_low for w in ("ак", "акк", "фб", "fb", "каб", "профіл", "профил", "шт", "ліміт", "лимит", "гео", "сша", "укр", "пол")):
            scores["issue_accounts"] += 85
    if entities.get("qty") and any(w in ctx_low for w in ("ак", "фб", "fb", "каб", "гео", "лім")):
        scores["issue_accounts"] += 60

    # 2. Картки / FBM / Білінг / Деклайн
    if any(w in ctx_low for w in ("карт", "card", "деклайн", "decline", "білінг", "биллинг", "billing", "fbm", "риск пеймент", "risk payment", "списан", "не списує", "ліміт карт", "поповн")):
        scores["card_issue"] += 85
    if entities.get("card_last4"):
        scores["card_issue"] += 65

    # 3. БМ / Піксель / Доступи
    if any(w in ctx_low for w in ("бм", "bm", "бізнес менеджер", "піксел", "пиксел", "pixel", "розшар", "расшар", "лінкан", "линкан", "прилін", "доступ", "інвайт", "инвайт", "фп", "фанк")):
        scores["bm_share"] += 80
    if entities.get("bm_id"):
        scores["bm_share"] += 60

    # 4. Чекпоінт / Бан / Проксі / AdsPower / 2FA
    if any(w in ctx_low for w in ("чек", "селфі", "селфи", "selfie", "зрд", "рд", "бан", "забанил", "вилетів", "вылетел", "проксі", "прокси", "proxy", "adspower", "адспавер", "2fa", "код", "апеляц", "апелляц", "лог", "парол")):
        scores["account_check"] += 80
    if entities.get("account_codes") and scores["issue_accounts"] < 50:
        scores["account_check"] += 50

    # 5. Закупівля / Фарм
    if any(w in ctx_low for w in ("закуп", "докуп", "купити", "купить", "постачальник", "селер", "селлер", "пачк", "баєрам на завтра", "дофарм")):
        scores["procurement"] += 95

    # 6. Фінанси / Таблиця / Звірка
    if any(w in ctx_low for w in ("звірк", "сверк", "таблиц", "спенд не", "usdt", "trc20", "оплат", "інвойс", "инвойс", "комісі", "комисси", "перерахуй")):
        scores["finance"] += 75

    # Загальні питальні або наказові конструкції
    if any(w in low for w in ("подивіться", "посмотрите", "перевір", "проверь", "допомож", "помог", "зроби", "сделай", "плз", "плиз", "please", "?", "потрібно", "нужно", "терміново", "срочно")):
        scores["general"] += 45

    best_cat = max(scores, key=lambda k: scores[k])
    best_score = scores[best_cat]

    if best_score < 40:
        return {
            "is_actionable": False,
            "category": "noise",
            "priority": "low",
            "confidence": 75,
            "title": "Інформаційне повідомлення",
            "description": clean[:200],
            "reasoning": "Не виявлено чіткого запиту чи дії для команди.",
            "suggested_reply": None,
            "entities": entities,
            "checklist": [],
        }

    # Пріоритет
    priority = "medium"
    if any(w in ctx_low for w in ("терміново", "срочно", "asap", "трафік стоїть", "трафик стоит", "стоп", "деклайн", "decline", "всі вилетіли", "горит", "❗️", "🚨", "!!!")):
        priority = "urgent"
    elif best_cat in ("card_issue", "issue_accounts", "account_check"):
        priority = "high"

    # Генерація людинозрозумілого заголовка
    buyer_tag = f" для {entities['buyer_name']}" if entities.get("buyer_name") else (f" ({entities['client_name']})" if entities.get("client_name") else "")
    cards_tag = f" ••{', ••'.join(entities['card_last4'])}" if entities.get("card_last4") else ""
    accs_tag = f" {', '.join(entities['account_codes'])}" if entities.get("account_codes") else ""

    if best_cat == "issue_accounts":
        q_str = f"{entities.get('qty') or 1} шт."
        g_str = f" ГЕО {entities['geo']}" if entities.get("geo") else ""
        l_str = f" (ліміт {entities['limit']})" if entities.get("limit") else ""
        title = f"Видати акаунти: {q_str}{g_str}{l_str}{buyer_tag}"
        reply = f"Прийнято! Готуємо {q_str}{g_str}{l_str}, зараз підберемо з пулу Ready та відпишемо."
    elif best_cat == "card_issue":
        if "деклайн" in ctx_low or "decline" in ctx_low:
            title = f"Вирішити деклайн по картці{cards_tag}{buyer_tag}"
        elif "ліміт" in ctx_low or "лимит" in ctx_low or "поповн" in ctx_low:
            title = f"Оновити ліміт / баланс картки{cards_tag}{buyer_tag}"
        else:
            title = f"Перевірити платіжну картку FBM{cards_tag}{buyer_tag}"
        reply = f"Взяли в роботу картку{cards_tag}. Перевіряємо статус і баланс у FBM Cards."
    elif best_cat == "bm_share":
        bm_str = f" BM {entities['bm_id']}" if entities.get("bm_id") else " БМ / Піксель"
        title = f"Розшарити доступ:{bm_str}{accs_tag}{buyer_tag}"
        reply = f"Прийнято, зараз розшаримо{bm_str} через AdsPower і відпишемо по готовності."
    elif best_cat == "account_check":
        title = f"Пройти чек / перевірити акаунт{accs_tag}{buyer_tag}"
        reply = f"Дивимось профіль{accs_tag} в AdsPower, перевіримо чек/проксі та оновимо статус."
    elif best_cat == "procurement":
        title = f"Закупівля / поповнення пулу розхідників{buyer_tag}"
        reply = "Зафіксували запит на закупівлю/фарм."
    elif best_cat == "finance":
        title = f"Звірка спенду та балансу таблиці{buyer_tag}"
        reply = f"Перевіряємо транзакції FBM та оновлюємо Google Таблицю{buyer_tag}."
    else:
        short_clean = re.sub(r"\s+", " ", clean)
        title = (short_clean[:72] + "…") if len(short_clean) > 72 else short_clean
        reply = "Прийнято в роботу, зараз перевіримо!"

    confidence = min(98, max(65, best_score + (10 if (entities.get("buyer_name") or entities.get("card_last4") or entities.get("account_codes")) else 0)))

    desc_parts = [f"Джерело: Telegram-група «{chat_title}» від {sender_label}."]
    if entities.get("buyer_name"):
        desc_parts.append(f"Баєр: {entities['buyer_name']}" + (f" (Команда: {entities['team_name']})" if entities.get("team_name") else ""))
    if entities.get("card_last4"):
        desc_parts.append(f"Картки FBM: ••{', ••'.join(entities['card_last4'])}")
    if entities.get("account_codes"):
        desc_parts.append(f"Акаунти: {', '.join(entities['account_codes'])}")
    if entities.get("bm_id"):
        desc_parts.append(f"BM ID: {entities['bm_id']}")
    if context_messages:
        desc_parts.append(f"Враховано контекст попередніх повідомлень у гілці ({len(context_messages)} шт.).")

    checklist = _build_checklist(best_cat, entities)

    return {
        "is_actionable": True,
        "category": best_cat,
        "priority": priority,
        "confidence": confidence,
        "title": title,
        "description": " | ".join(desc_parts),
        "reasoning": f"Визначено намір «{best_cat}» за ключовими маркерами та прив'язкою до сутностей БД.",
        "suggested_reply": reply,
        "entities": entities,
        "checklist": checklist,
    }


def _call_llm_analyzer(
    cfg: Dict[str, Any],
    raw_text: str,
    context_messages: List[str],
    entities: Dict[str, Any],
    sender_label: str,
    chat_title: str,
    topic_filter: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Викликає OpenAI або Gemini API для глибокого розуміння контексту (якщо налаштовано ключ)."""
    api_key = cfg.get("api_key")
    if not api_key:
        return None

    provider = cfg.get("provider", "hybrid")
    if provider == "domain_nlp":
        return None

    model = cfg.get("model") or "gpt-4o-mini"
    sys_prompt = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    if topic_filter:
        sys_prompt += f"\nДодаткове правило для цієї групи: {topic_filter}"

    user_prompt = (
        f"Група: {chat_title}\n"
        f"Відправник: {sender_label}\n"
        f"Попередні повідомлення в чаті (контекст):\n"
        + ("\n".join(f"- {m}" for m in context_messages) if context_messages else "(немає)")
        + f"\n\nНове повідомлення:\n{raw_text}\n\n"
        f"Знайдені сутності з бази даних:\n{json.dumps(entities, ensure_ascii=False)}\n\n"
        "Поверни СУВОРО валідний JSON об'єкт з полями:\n"
        '{"is_actionable": true/false, "category": "issue_accounts|card_issue|bm_share|account_check|procurement|finance|general|noise", '
        '"priority": "low|medium|high|urgent", "confidence": 0..100, "title": "Коротка чітка назва задачі українською", '
        '"description": "Детальний опис що треба зробити", "reasoning": "Чому прийнято таке рішення", '
        '"suggested_reply": "Текст відповіді в чат", "checklist": ["Крок 1", "Крок 2"]}'
    )

    try:
        if "gemini" in model.lower() or provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            resp = httpx.post(
                url,
                json={
                    "contents": [{"parts": [{"text": sys_prompt + "\n\n" + user_prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
                },
                timeout=12.0,
            )
            resp.raise_for_status()
            data = resp.json()
            text_out = data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=12.0,
            )
            resp.raise_for_status()
            text_out = resp.json()["choices"][0]["message"]["content"]

        parsed = json.loads(text_out)
        raw_steps = parsed.get("checklist") or []
        checklist = [
            {"id": f"chk-{i+1}", "text": s if isinstance(s, str) else s.get("text", ""), "done": False}
            for i, s in enumerate(raw_steps)
        ]
        if not checklist and parsed.get("is_actionable"):
            checklist = _build_checklist(parsed.get("category", "general"), entities)

        return {
            "is_actionable": bool(parsed.get("is_actionable", False)),
            "category": parsed.get("category", "general"),
            "priority": parsed.get("priority", "medium"),
            "confidence": int(parsed.get("confidence", 85)),
            "title": parsed.get("title") or "Нова задача з Telegram",
            "description": parsed.get("description") or "",
            "reasoning": parsed.get("reasoning") or "Проаналізовано LLM-моделлю.",
            "suggested_reply": parsed.get("suggested_reply"),
            "entities": entities,
            "checklist": checklist,
        }
    except Exception:
        return None


def analyze_telegram_message(
    db: Session,
    raw_text: str,
    sender_username: Optional[str] = None,
    sender_name: Optional[str] = None,
    chat_title: str = "Робочий чат",
    context_messages: Optional[List[str]] = None,
    reply_text: Optional[str] = None,
    group_team_id: Optional[uuid.UUID] = None,
    group_client_id: Optional[uuid.UUID] = None,
    topic_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Головна точка входу для аналізу повідомлення з Telegram-групи."""
    ctx = context_messages or []
    # Сутності витягуємо з самого повідомлення (+ тексту повідомлення, на яке зроблено прямий reply)
    entity_source_text = f"{reply_text}\n{raw_text}" if reply_text else (raw_text or "")
    entities = _resolve_db_entities(
        db,
        text=entity_source_text,
        sender_username=sender_username,
        sender_name=sender_name,
        group_team_id=group_team_id,
        group_client_id=group_client_id,
    )
    sender_label = (
        f"@{sender_username.lstrip('@')} ({sender_name})"
        if sender_username and sender_name
        else (f"@{sender_username.lstrip('@')}" if sender_username else (sender_name or "Учасник"))
    )

    cfg = get_ai_config(db)
    llm_res = _call_llm_analyzer(
        cfg=cfg,
        raw_text=raw_text,
        context_messages=ctx,
        entities=entities,
        sender_label=sender_label,
        chat_title=chat_title,
        topic_filter=topic_filter,
    )
    if llm_res is not None:
        llm_res["engine"] = f"llm:{cfg.get('model', 'gpt-4o-mini')}"
        return llm_res

    res = _domain_heuristic_analyze(
        raw_text=raw_text,
        context_messages=[reply_text] if reply_text else [],
        entities=entities,
        sender_label=sender_label,
        chat_title=chat_title,
    )
    res["engine"] = "domain_ai_v2"
    return res
