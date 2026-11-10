"""Сповіщення виконавцю про призначення задачі і зміну її статусу."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import TeamTask, UserNotification

STATUS_LABELS = {
    "inbox": "Вхідні",
    "todo": "До виконання",
    "in_progress": "В роботі",
    "review": "На перевірці",
    "done": "Виконано",
    "rejected": "Відхилено",
}


def _add(db: Session, user_id: uuid.UUID | None, kind: str, title: str, message: str, link: str) -> None:
    if user_id is None:
        return
    db.add(UserNotification(user_id=user_id, kind=kind, title=title, message=message, link=link))


def notify_assigned(db: Session, task: TeamTask, actor_id: uuid.UUID | None = None) -> None:
    if not task.assignee_id or task.assignee_id == actor_id:
        return
    code = task.code or "Задача"
    _add(
        db,
        task.assignee_id,
        "task_assigned",
        f"Вам призначено {code}",
        task.title,
        "/tasks",
    )


def notify_status(db: Session, task: TeamTask, old_status: str, new_status: str, actor_id: uuid.UUID | None = None) -> None:
    if old_status == new_status:
        return
    code = task.code or "Задача"
    old_label = STATUS_LABELS.get(old_status, old_status)
    new_label = STATUS_LABELS.get(new_status, new_status)
    targets = []
    for uid in (task.assignee_id, task.creator_id):
        if uid and uid != actor_id and uid not in targets:
            targets.append(uid)
    for uid in targets:
        _add(
            db,
            uid,
            "task_status",
            f"{code}: {old_label} → {new_label}",
            task.title,
            "/tasks",
        )
