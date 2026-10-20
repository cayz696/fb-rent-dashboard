from __future__ import annotations
"""Локальний статус репозиторію. Оновлення коду з браузера вимкнене: pull виконує лише desktop/update.sh."""
from pathlib import Path
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import admin_only, current_user
from app.core.db import get_db
from app.models import SystemState, User

router = APIRouter(prefix="/api/system", tags=["system"])

ROOT_DIR = Path(__file__).resolve().parents[5]


def _run_git(args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (res.stdout or "") + (res.stderr or "")
        return res.returncode, out.strip()
    except Exception as e:
        return 1, str(e)


@router.get("/status")
def system_status(
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    code_git, _ = _run_git(["rev-parse", "--is-inside-work-tree"])
    git_initialized = code_git == 0

    commit = "—"
    branch = "main"
    remote_url = ""
    behind_count = 0
    last_commit_msg = ""

    if git_initialized:
        c1, out1 = _run_git(["rev-parse", "--short", "HEAD"])
        if c1 == 0 and out1:
            commit = out1
        c2, out2 = _run_git(["branch", "--show-current"])
        if c2 == 0 and out2:
            branch = out2
        c3, out3 = _run_git(["remote", "get-url", "origin"])
        if c3 == 0 and out3:
            remote_url = out3
        c4, out4 = _run_git(["log", "-1", "--pretty=%s (%ci)"])
        if c4 == 0 and out4:
            last_commit_msg = out4

    st_tr = db.get(SystemState, "fbm_spend_tracker_state")
    return {
        "git_initialized": git_initialized,
        "commit": commit,
        "branch": branch,
        "remote_url": remote_url,
        "last_commit_msg": last_commit_msg,
        "behind_count": behind_count,
        "auto_sync_interval_hours": 3.5,
        "reconcile_interval_hours": 24,
        "last_spend_snapshot": st_tr.value.get("last_recorded_at") if st_tr and st_tr.value else None,
    }


_UPDATE_OFF = "Оновлення коду з браузера вимкнене. На машині з дашбордом запустіть desktop/update.sh."


@router.post("/github-remote")
def set_github_remote(_: User = Depends(admin_only)):
    raise HTTPException(410, _UPDATE_OFF)


@router.post("/github-update")
def github_update(_: User = Depends(admin_only)):
    raise HTTPException(410, _UPDATE_OFF)
