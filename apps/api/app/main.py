from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.routes import accounts, adspower, auth, bridge, buyers, catalog, clover, dashboard, fbm, finance, imports, notifications, reports, requests, system, users
from app.core.db import SessionLocal
from app.models import Team
from app.services import buyers_sync
from sqlalchemy import select


async def _periodic_fbm_and_sheets_loop():
    """Фоновий цикл: кожні 3.5 години фіксує спенд по картках FBM,
    автоматично вносить актуальні дані в Google-таблиці команд,
    і раз на добу звіряє суми з кабінетом FBM Cards."""
    ticks = 0
    while True:
        await asyncio.sleep(3.5 * 3600)
        ticks += 1
        try:
            with SessionLocal() as db:
                # 1. Зафіксувати свіжий спенд з FBM у БД
                buyers_sync.record_card_spends(db, refresh_fbm=True)

                # 2. Автоматично оновити дані в Google-таблицях команд
                for t in db.scalars(select(Team)).all():
                    try:
                        if t.sheet_webhook_url:
                            buyers_sync.push_team_spends_to_sheet(db, t)
                        elif t.sheet_url:
                            buyers_sync.fetch_and_sync_team_sheet(db, t)
                    except Exception:
                        pass

                # 3. Добова звірка раз на 24 години
                if ticks % 7 == 0:
                    buyers_sync.reconcile_fbm_spend(db, fetch_live=True)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        task = asyncio.create_task(_periodic_fbm_and_sheets_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="FB Rent API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)

# Простий rate-limit для кроків входу (на процес; для одного інстанса достатньо)
_hits: dict[str, deque] = defaultdict(deque)
LIMITS = {"/api/auth/login": 10, "/api/auth/2fa/verify": 10, "/api/clover/spend": 120}  # запитів/хв з одного IP
WINDOW = 60


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    limit = LIMITS.get(request.url.path)
    if limit:
        key = f"{request.client.host if request.client else '?'}:{request.url.path}"
        q, now = _hits[key], time.monotonic()
        while q and now - q[0] > WINDOW:
            q.popleft()
        if len(q) >= limit:
            return JSONResponse({"detail": "Забагато спроб, зачекайте хвилину"}, status_code=429)
        q.append(now)
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"ok": True}


for r in (
    auth.router,
    accounts.router,
    catalog.router,
    dashboard.router,
    users.router,
    requests.router,
    clover.router,
    bridge.router,
    finance.router,
    imports.router,
    adspower.router,
    notifications.router,
    fbm.router,
    buyers.router,
    reports.router,
    system.router,
):
    app.include_router(r)
