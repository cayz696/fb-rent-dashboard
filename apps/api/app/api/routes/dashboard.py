from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.services import signals as signals_svc
from app.services import spend as spend_svc
from app.core.db import get_db
from app.models import Account, OffReason, Request, RequestStatus, Stage, User
from app.schemas.api import DashboardOut, SignalOut

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/signals", response_model=list[SignalOut])
def signals(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return signals_svc.compute(db)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _: User = Depends(current_user)):
    by_stage = dict(db.execute(select(Account.stage, func.count()).group_by(Account.stage)).all())
    funnel = {s.value: by_stage.get(s, 0) for s in Stage}
    off = dict(
        db.execute(select(Account.off_reason, func.count()).where(Account.stage == Stage.off).group_by(Account.off_reason)).all()
    )
    off_breakdown = {r.value: off.get(r, 0) for r in OffReason}
    req_counts = dict(db.execute(select(Request.status, func.count()).group_by(Request.status)).all())
    pool = sum(v for k, v in by_stage.items() if k not in (Stage.off, Stage.sold))  # активний пул без off/продано

    # Розрахунок спенду FBM Cards
    today_dt = spend_svc.today_kyiv()
    from app.models import BuyerDailySpend
    fbm_today = db.scalar(select(func.sum(BuyerDailySpend.spend_fbm)).where(BuyerDailySpend.date == today_dt))
    fbm_total = db.scalar(select(func.sum(BuyerDailySpend.spend_fbm)))

    return DashboardOut(
        spend_today=spend_svc.spend_today_total(db),
        issued=by_stage.get(Stage.issued, 0),
        pool_total=pool,
        ready=by_stage.get(Stage.ready, 0),
        requests_queue=req_counts.get(RequestStatus.new, 0) + req_counts.get(RequestStatus.proposed, 0),
        requests_pending_approval=req_counts.get(RequestStatus.proposed, 0),
        funnel=funnel,
        off_breakdown=off_breakdown,
        signals_count=len(signals_svc.compute(db)),
        clover_last_received=spend_svc.last_received(db),
        fbm_spend_today=fbm_today,
        fbm_spend_total=fbm_total,
    )
