"""Керування десктоп-системою та оновленням через GitHub."""
from pathlib import Path
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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


class RemoteIn(BaseModel):
    remote_url: str


@router.get("/status")
def system_status(
    check_remote: bool = False,
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

        if check_remote and remote_url:
            _run_git(["fetch", "origin", branch], timeout=15)
            c5, out5 = _run_git(["rev-list", f"HEAD..origin/{branch}", "--count"])
            if c5 == 0 and out5.isdigit():
                behind_count = int(out5)

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


@router.post("/github-remote")
def set_github_remote(body: RemoteIn, _: User = Depends(admin_only)):
    url = body.remote_url.strip()
    if not url:
        raise HTTPException(400, "Вкажіть URL репозиторію GitHub")
    code, _ = _run_git(["rev-parse", "--is-inside-work-tree"])
    if code != 0:
        _run_git(["init", "-b", "main"])
    c_rem, _ = _run_git(["remote", "get-url", "origin"])
    if c_rem == 0:
        rc, out = _run_git(["remote", "set-url", "origin", url])
    else:
        rc, out = _run_git(["remote", "add", "origin", url])
    if rc != 0:
        raise HTTPException(400, f"Помилка налаштування remote: {out}")
    return {"ok": True, "remote_url": url}


@router.post("/github-update")
def github_update(_: User = Depends(admin_only)):
    code, _ = _run_git(["rev-parse", "--is-inside-work-tree"])
    if code != 0:
        raise HTTPException(400, "Git-репозиторій не ініціалізовано")
    c_rem, rem_url = _run_git(["remote", "get-url", "origin"])
    if c_rem != 0 or not rem_url:
        raise HTTPException(400, "Спочатку вкажіть GitHub Remote URL у налаштуваннях")

    _, branch = _run_git(["branch", "--show-current"])
    branch = branch or "main"

    rc_pull, out_pull = _run_git(["pull", "--ff-only", "origin", branch], timeout=45)
    if rc_pull != 0:
        raise HTTPException(400, f"Не вдалося оновити з GitHub: {out_pull}")

    # Автоматично проганяємо міграції БД після git pull
    alembic_bin = ROOT_DIR / "apps" / "api" / ".venv" / "bin" / "alembic"
    mig_out = ""
    if alembic_bin.exists():
        res = subprocess.run(
            [str(alembic_bin), "upgrade", "head"],
            cwd=str(ROOT_DIR / "apps" / "api"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        mig_out = (res.stdout or "") + (res.stderr or "")

    _, new_commit = _run_git(["rev-parse", "--short", "HEAD"])
    return {
        "ok": True,
        "commit": new_commit,
        "git_output": out_pull or "Вже встановлено останню версію",
        "migrations_output": mig_out.strip(),
    }
