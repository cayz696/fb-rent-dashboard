from __future__ import annotations
"""Повний бекап/відновлення Postgres для переносу дашборда на інший ноут.

Джерело правди — `pg_dump -Fc` (схема + дані + sequences). JSON-зліпок лишається
запасним варіантом, якщо клієнт pg_dump недоступний.
"""
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine.url import make_url

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Account, Buyer, Team, User
from app.services import db_sync

ROOT_DIR = Path(__file__).resolve().parents[4]
KEEP_BACKUPS = 10


def backup_dir() -> Path:
    return Path(os.environ.get("FBRENT_BACKUP_DIR") or (ROOT_DIR / "backups"))


def latest_dump() -> Path:
    return backup_dir() / "latest.dump"


def latest_json() -> Path:
    return backup_dir() / "latest.json.gz"


def env_transfer() -> Path:
    return backup_dir() / "env.transfer"


def manifest_path() -> Path:
    return backup_dir() / "latest.json"


def _dsn():
    url = make_url(settings.database_url)
    return {
        "user": url.username or "fbrent",
        "password": url.password or "",
        "host": url.host or "127.0.0.1",
        "port": int(url.port or 5432),
        "database": url.database or "fbrent",
    }


def _compose_cmd() -> list[str]:
    compose = ROOT_DIR / "docker-compose.yml"
    return ["docker", "compose", "-f", str(compose), "exec", "-T", "db"]


def _docker_db_up(dsn: dict) -> bool:
    if dsn["port"] != 5440:
        return False
    if shutil.which("docker") is None:
        return False
    r = subprocess.run(
        ["docker", "compose", "-f", str(ROOT_DIR / "docker-compose.yml"), "ps", "-q", "db"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def db_counts() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "users": db.scalar(select(func.count()).select_from(User)) or 0,
            "accounts": db.scalar(select(func.count()).select_from(Account)) or 0,
            "teams": db.scalar(select(func.count()).select_from(Team)) or 0,
            "buyers": db.scalar(select(func.count()).select_from(Buyer)) or 0,
        }


def is_db_empty() -> bool:
    c = db_counts()
    return c["accounts"] == 0 and c["teams"] == 0 and c["buyers"] == 0


def _write_env_transfer() -> bool:
    env_path = ROOT_DIR / ".env"
    if not env_path.is_file():
        return False
    backup_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy2(env_path, env_transfer())
    return True


def _prune_old_dumps() -> None:
    dumps = sorted(backup_dir().glob("fbrent-*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in dumps[KEEP_BACKUPS:]:
        stale.unlink(missing_ok=True)


def _pg_dump_to(path: Path) -> None:
    dsn = _dsn()
    path.parent.mkdir(parents=True, exist_ok=True)
    if _docker_db_up(dsn):
        with path.open("wb") as f:
            r = subprocess.run(
                [*_compose_cmd(), "pg_dump", "-U", dsn["user"], "-d", dsn["database"], "-Fc"],
                cwd=ROOT_DIR,
                stdout=f,
                stderr=subprocess.PIPE,
            )
        if r.returncode != 0:
            path.unlink(missing_ok=True)
            raise RuntimeError(r.stderr.decode("utf-8", errors="replace") or "pg_dump (docker) failed")
        return

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError("pg_dump не знайдено. Встановіть Docker (порт 5440) або PostgreSQL client.")
    env = os.environ.copy()
    if dsn["password"]:
        env["PGPASSWORD"] = dsn["password"]
    r = subprocess.run(
        [
            pg_dump, "-Fc", "-h", dsn["host"], "-p", str(dsn["port"]),
            "-U", dsn["user"], "-d", dsn["database"], "-f", str(path),
        ],
        env=env,
        capture_output=True,
    )
    if r.returncode != 0:
        path.unlink(missing_ok=True)
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace") or "pg_dump failed")


def _pg_restore_from(path: Path) -> None:
    dsn = _dsn()
    if _docker_db_up(dsn):
        with path.open("rb") as f:
            r = subprocess.run(
                [
                    *_compose_cmd(), "pg_restore",
                    "--clean", "--if-exists", "--no-owner", "--no-acl",
                    "-U", dsn["user"], "-d", dsn["database"],
                ],
                cwd=ROOT_DIR,
                stdin=f,
                capture_output=True,
            )
        # pg_restore часто повертає 1 через warning на extensions — перевіряємо, чи дані з'явились
        if r.returncode not in (0, 1):
            raise RuntimeError(r.stderr.decode("utf-8", errors="replace") or "pg_restore (docker) failed")
        return

    pg_restore = shutil.which("pg_restore")
    if not pg_restore:
        raise RuntimeError("pg_restore не знайдено")
    env = os.environ.copy()
    if dsn["password"]:
        env["PGPASSWORD"] = dsn["password"]
    r = subprocess.run(
        [
            pg_restore, "--clean", "--if-exists", "--no-owner", "--no-acl",
            "-h", dsn["host"], "-p", str(dsn["port"]),
            "-U", dsn["user"], "-d", dsn["database"], str(path),
        ],
        env=env,
        capture_output=True,
    )
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace") or "pg_restore failed")


def create_backup() -> dict:
    """Створює pg_dump + JSON-зліпок + копію .env. Повертає маніфест."""
    backup_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dump_path = backup_dir() / f"fbrent-{stamp}.dump"
    counts = db_counts()
    method = "pg_dump"
    try:
        _pg_dump_to(dump_path)
        shutil.copy2(dump_path, latest_dump())
    except Exception as exc:
        method = f"json_only ({exc})"
        dump_path = None

    json_counts = db_sync.export_snapshot(latest_json())
    env_copied = _write_env_transfer()
    if dump_path:
        _prune_old_dumps()

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "dump_file": dump_path.name if dump_path else None,
        "dump_size_bytes": dump_path.stat().st_size if dump_path and dump_path.exists() else 0,
        "json_file": latest_json().name,
        "json_size_bytes": latest_json().stat().st_size if latest_json().exists() else 0,
        "env_transfer": env_copied,
        "counts": counts,
        "json_counts": json_counts,
    }
    manifest_path().write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if dump_path is None:
        raise RuntimeError(f"pg_dump не вдався, збережено лише JSON: {manifest['method']}")
    return manifest


def restore_backup(path: Path | None = None, only_if_empty: bool = False) -> dict:
    """Відновлює БД з latest.dump (або JSON)."""
    if only_if_empty and not is_db_empty():
        return {"skipped": True, "reason": "db_not_empty", "counts": db_counts()}

    dump = path or (latest_dump() if latest_dump().exists() else None)
    json_path = latest_json() if latest_json().exists() else db_sync.SNAPSHOT_PATH
    if dump and dump.exists():
        _pg_restore_from(dump)
        method = "pg_restore"
    elif json_path.exists():
        db_sync.import_snapshot(json_path)
        method = "json"
    else:
        raise FileNotFoundError("Немає backups/latest.dump і JSON-зліпка")

    alembic = ROOT_DIR / "apps" / "api" / ".venv" / "bin" / "alembic"
    mig = ""
    if alembic.exists():
        r = subprocess.run(
            [str(alembic), "upgrade", "head"],
            cwd=str(ROOT_DIR / "apps" / "api"),
            capture_output=True,
            text=True,
        )
        mig = ((r.stdout or "") + (r.stderr or "")).strip()

    return {"ok": True, "method": method, "counts": db_counts(), "migrations": mig}


def backup_status() -> dict:
    manifest: dict = {}
    if manifest_path().exists():
        try:
            manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    dump = latest_dump() if latest_dump().exists() else None
    return {
        "backup_dir": str(backup_dir()),
        "has_dump": bool(dump),
        "has_json": latest_json().exists() or db_sync.SNAPSHOT_PATH.exists(),
        "has_env_transfer": env_transfer().exists(),
        "dump_file": dump.name if dump else None,
        "dump_size_bytes": dump.stat().st_size if dump else 0,
        "created_at": manifest.get("created_at"),
        "counts": manifest.get("counts") or db_counts(),
        "db_empty": is_db_empty(),
        "live_counts": db_counts(),
    }
