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


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    c = sub.add_parser("create-user")
    c.add_argument("username"); c.add_argument("name"); c.add_argument("role", choices=[r.value for r in Role])
    c.add_argument("--password")
    c.set_defaults(fn=create_user)
    sub.add_parser("seed-demo").set_defaults(fn=seed_demo)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
