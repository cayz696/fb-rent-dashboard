from __future__ import annotations
"""Експорт та імпорт повного зліпка бази даних (JSON.GZ) для синхронізації між ноутбуками."""
from datetime import date, datetime
from decimal import Decimal
import gzip
import json
from pathlib import Path
import sys
from uuid import UUID

from sqlalchemy import Date, DateTime, Integer, MetaData, Numeric, Uuid, text
from app.core.db import engine

# Топологічний порядок таблиць (від батьківських до дочірніх по Foreign Keys)
TABLES_ORDER = [
    "users",
    "suppliers",
    "batches",
    "clients",
    "client_payments",
    "accounts",
    "account_events",
    "spend_snapshots",
    "requests",
    "bridge_commands",
    "system_state",
    "teams",
    "buyers",
    "card_spend_logs",
    "buyer_daily_spends",
    "fbm_reconciliations",
    "expense_categories",
    "expenses",
    "telegram_groups",
    "team_tasks",
    "telegram_message_logs",
]

SNAPSHOT_PATH = Path(__file__).resolve().parents[4] / "desktop" / "db_snapshot.json.gz"


def _serialize_val(v):
    if v is None:
        return None
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dict, list, bool, int, float, str)):
        return v
    return str(v)


def _deserialize_row(tbl, row: dict) -> dict:
    out = {}
    for col in tbl.columns:
        k = col.name
        if k not in row:
            continue
        val = row[k]
        if val is None:
            out[k] = None
            continue
        if isinstance(col.type, DateTime) and isinstance(val, str):
            out[k] = datetime.fromisoformat(val)
        elif isinstance(col.type, Date) and isinstance(val, str):
            out[k] = date.fromisoformat(val[:10])
        elif isinstance(col.type, Numeric) and isinstance(val, (str, int, float)):
            out[k] = Decimal(str(val))
        elif isinstance(col.type, Uuid) and isinstance(val, str):
            out[k] = UUID(val)
        else:
            out[k] = val
    return out


def export_snapshot(out_path: Path = SNAPSHOT_PATH) -> dict[str, int]:
    meta = MetaData()
    meta.reflect(bind=engine)
    data: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}

    with engine.connect() as conn:
        for tname in TABLES_ORDER:
            if tname not in meta.tables:
                continue
            tbl = meta.tables[tname]
            rows = conn.execute(tbl.select()).mappings().all()
            serialized = [dict(r) for r in rows]
            data[tname] = serialized
            counts[tname] = len(serialized)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=_serialize_val)
    return counts


def import_snapshot(in_path: Path = SNAPSHOT_PATH) -> dict[str, int]:
    if not in_path.exists():
        raise FileNotFoundError(f"Зліпок БД не знайдено: {in_path}")

    with gzip.open(in_path, "rt", encoding="utf-8") as f:
        data: dict[str, list[dict]] = json.load(f)

    meta = MetaData()
    meta.reflect(bind=engine)
    counts: dict[str, int] = {}

    existing_tables = [t for t in TABLES_ORDER if t in meta.tables]
    with engine.begin() as conn:
        if existing_tables:
            trunc_sql = "TRUNCATE TABLE " + ", ".join(existing_tables) + " RESTART IDENTITY CASCADE"
            conn.execute(text(trunc_sql))

        for tname in existing_tables:
            rows = data.get(tname) or []
            if not rows:
                counts[tname] = 0
                continue
            tbl = meta.tables[tname]
            parsed_rows = [_deserialize_row(tbl, r) for r in rows]
            for i in range(0, len(parsed_rows), 1000):
                chunk = parsed_rows[i : i + 1000]
                conn.execute(tbl.insert(), chunk)
            counts[tname] = len(parsed_rows)

        for tname in existing_tables:
            tbl = meta.tables[tname]
            if "id" in tbl.c and isinstance(tbl.c["id"].type, Integer):
                seq_name = conn.execute(text(f"SELECT pg_get_serial_sequence('{tname}', 'id')")).scalar()
                if seq_name:
                    conn.execute(
                        text(
                            f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM {tname}), 1), true)"
                        )
                    )

    return counts


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "export"
    if cmd == "export":
        res = export_snapshot()
        print("Експортовано зліпок БД у desktop/db_snapshot.json.gz:", res)
    elif cmd == "import":
        res = import_snapshot()
        print("Імпортовано зліпок БД із desktop/db_snapshot.json.gz:", res)
