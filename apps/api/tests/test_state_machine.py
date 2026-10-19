from __future__ import annotations
import pytest

from app.models.enums import OffReason, Stage
from app.services.state_machine import FLOW, TransitionError, TransitionInput, next_stages, validate

S = Stage


def t(cur, target, **kw):
    validate(TransitionInput(current=cur, current_off_reason=kw.pop("cur_reason", None), target=target, **kw))


def test_happy_path_chain():
    for a, b in zip(FLOW[:-2], FLOW[1:-1]):
        t(a, b)
    t(S.ready, S.issued, client_id=1, confirm_manual=True)


@pytest.mark.parametrize("cur,target", [
    (S.purchased, S.ready), (S.purchased, S.issued), (S.warmup, S.purchased),
    (S.ready, S.checking), (S.issued, S.ready), (S.checking, S.issued), (S.returned, S.issued),
])
def test_forbidden(cur, target):
    with pytest.raises(TransitionError):
        t(cur, target)


def test_off_requires_reason_and_comment():
    with pytest.raises(TransitionError):
        t(S.warmup, S.off)
    with pytest.raises(TransitionError):
        t(S.warmup, S.off, off_reason=OffReason.ban)
    t(S.warmup, S.off, off_reason=OffReason.ban, comment="бан")


def test_any_stage_to_off():
    for s in Stage:
        if s not in (S.off, S.sold):  # off і sold — термінальні
            assert S.off in next_stages(s)


def test_sold_is_terminal_and_reachable():
    assert next_stages(S.sold) == set()
    for s in (S.warmup, S.ready, S.issued):
        assert S.sold in next_stages(s)
    # з purchased одразу продати не можна
    assert S.sold not in next_stages(S.purchased)


def test_off_back_to_ready_only_reserve_paused():
    t(S.off, S.ready, cur_reason=OffReason.reserve)
    t(S.off, S.ready, cur_reason=OffReason.paused)
    for r in (OffReason.ban, OffReason.returned, OffReason.written_off):
        with pytest.raises(TransitionError):
            t(S.off, S.ready, cur_reason=r)


def test_returned_to_ready_or_off():
    t(S.issued, S.returned)
    t(S.returned, S.ready)
    t(S.returned, S.off, off_reason=OffReason.written_off, comment="списано")


def test_issue_needs_client_and_request_or_confirm():
    with pytest.raises(TransitionError):
        t(S.ready, S.issued, confirm_manual=True)
    with pytest.raises(TransitionError):
        t(S.ready, S.issued, client_id=1)
    t(S.ready, S.issued, client_id=1, request_id=5)
