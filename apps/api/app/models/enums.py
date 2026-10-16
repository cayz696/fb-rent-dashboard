import enum


class Stage(str, enum.Enum):
    purchased = "purchased"
    in_adspower = "in_adspower"
    bm_created = "bm_created"
    phone_linked = "phone_linked"
    warmup = "warmup"
    card_linked = "card_linked"
    checking = "checking"
    ready = "ready"
    issued = "issued"
    sold = "sold"
    returned = "returned"
    off = "off"


class OffReason(str, enum.Enum):
    ban = "ban"
    reserve = "reserve"
    paused = "paused"
    returned = "returned"
    written_off = "written_off"


class Role(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


class RequestStatus(str, enum.Enum):
    new = "new"
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    done = "done"


class CommandStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    ok = "ok"
    error = "error"
