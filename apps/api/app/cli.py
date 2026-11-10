from __future__ import annotations
"""CLI: python -m app.cli create-user <username> <name> <role> [--password P]  |  seed-demo"""
import argparse
import getpass

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Role, User


def create_user(args):
    pw = args.password or getpass.getpass("Пароль: ")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == args.username)):
            raise SystemExit("Користувач уже існує")
        db.add(User(username=args.username, name=args.name, role=Role(args.role), password_hash=hash_password(pw)))
        db.commit()
    print(f"OK: {args.username} ({args.role}). 2FA налаштується при першому вході.")


def seed_demo(_):
    from app.services import accounts as svc
    from app.models import Batch, Client, Supplier

    with SessionLocal() as db:
        if db.scalar(select(Supplier)):
            raise SystemExit("Дані вже є")
        sup = [Supplier(name="Atlas"), Supplier(name="Delta")]
        cl = [Client(name="Nord", telegram_usernames=["nord_media"]), Client(name="Vega", telegram_usernames=["vega_team"])]
        db.add_all(sup + cl)
        db.flush()
        for s, n in zip(sup, (6, 4)):
            b = Batch(supplier_id=s.id, qty=n, unit_cost=45)
            db.add(b)
            db.flush()
            for _ in range(n):
                svc.create_account(db, "seed", supplier_id=s.id, batch_id=b.id, purchase_cost=b.unit_cost)
        db.commit()
    print("Демо-дані створено")


def backup(_):
    from app.services.machine_backup import create_backup
    res = create_backup()
    print("Бекап збережено:", res)


def restore(args):
    from pathlib import Path
    from app.services.machine_backup import restore_backup
    path = Path(args.file) if args.file else None
    res = restore_backup(path, only_if_empty=args.if_empty)
    print("Відновлення:", res)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    c = sub.add_parser("create-user")
    c.add_argument("username"); c.add_argument("name"); c.add_argument("role", choices=[r.value for r in Role])
    c.add_argument("--password")
    c.set_defaults(fn=create_user)
    sub.add_parser("seed-demo").set_defaults(fn=seed_demo)
    sub.add_parser("backup").set_defaults(fn=backup)
    r = sub.add_parser("restore")
    r.add_argument("--file", help="Шлях до .dump (за замовч. backups/latest.dump)")
    r.add_argument("--if-empty", action="store_true", help="Не чіпати БД, якщо в ній уже є дані")
    r.set_defaults(fn=restore)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
