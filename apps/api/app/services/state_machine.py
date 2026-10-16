"""Статус-машина акаунта (розділ 5 ТЗ). Чиста логіка без БД."""
from dataclasses import dataclass

from app.models.enums import OffReason, Stage

S = Stage

# purchased → in_adspower → bm_created → phone_linked → warmup → card_linked → checking → ready → issued
FLOW: list[Stage] = [
    S.purchased, S.in_adspower, S.bm_created, S.phone_linked, S.warmup, S.card_linked, S.checking, S.ready, S.issued,
]

ALLOWED: dict[Stage, set[Stage]] = {a: {b} for a, b in zip(FLOW, FLOW[1:])}
ALLOWED[S.issued] = {S.returned}
ALLOWED[S.returned] = {S.ready}
ALLOWED[S.off] = {S.ready}  # лише для reserve | paused, див. next_stages
# будь-який етап → off
for _s in Stage:
    if _s != S.off:
        ALLOWED[_s] = ALLOWED.get(_s, set()) | {S.off}

# Продаж — окремий напрямок (ТЗ v2): продати можна «робочі» акаунти, термінально
SELLABLE = {S.warmup, S.card_linked, S.checking, S.ready, S.issued, S.returned}
for _s in SELLABLE:
    ALLOWED[_s] = ALLOWED.get(_s, set()) | {S.sold}
ALLOWED[S.sold] = set()  # термінальний (навіть не в off)

CHECK_HOURS = 24
CHECK_WARN_MINUTES = 30


class TransitionError(Exception):
    """Недозволений перехід або порушене правило → HTTP 409."""


@dataclass
class TransitionInput:
    current: Stage
    current_off_reason: OffReason | None
    target: Stage
    off_reason: OffReason | None = None
    comment: str | None = None
    client_id: object | None = None      # клієнт акаунта (поточний або з запиту)
    request_id: object | None = None
    confirm_manual: bool = False
    sold_to: str | None = None           # покупець (для sold)
    sale_price: object | None = None     # ціна продажу (для sold)


def next_stages(current: Stage, off_reason: OffReason | None = None) -> set[Stage]:
    allowed = set(ALLOWED[current])
    if current == S.off and off_reason not in (OffReason.reserve, OffReason.paused):
        allowed.discard(S.ready)
    return allowed


def validate(t: TransitionInput) -> None:
    if t.target not in next_stages(t.current, t.current_off_reason):
        raise TransitionError(f"Перехід {t.current.value} → {t.target.value} не дозволений")
    if t.target == S.off:
        if t.off_reason is None:
            raise TransitionError("Для переходу в off потрібна причина (off_reason)")
        if not (t.comment and t.comment.strip()):
            raise TransitionError("Для переходу в off потрібен коментар")
    if t.target == S.issued:
        if t.client_id is None:
            raise TransitionError("Для видачі потрібен клієнт")
        if t.request_id is None and not t.confirm_manual:
            raise TransitionError("Видача потребує заявки або ручного підтвердження адміна")
    if t.target == S.sold:
        if not (t.sold_to and t.sold_to.strip()):
            raise TransitionError("Для продажу потрібно вказати покупця")
        if t.sale_price is None:
            raise TransitionError("Для продажу потрібна ціна")
