import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file() -> None:
    """Локальний .env (поряд із bridge або в корені репозиторію); змінні середовища мають пріоритет."""
    for base in (Path.cwd(), Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[3]):
        f = base / ".env"
        if f.is_file():
            for line in f.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return


@dataclass(frozen=True)
class Config:
    server_ws_url: str
    token: str
    adspower_url: str
    adspower_key: str

    @staticmethod
    def load() -> "Config":
        _load_env_file()
        url, token = os.environ.get("BRIDGE_SERVER_WS_URL", ""), os.environ.get("BRIDGE_TOKEN", "")
        if not url or not token:
            raise SystemExit("Потрібні BRIDGE_SERVER_WS_URL і BRIDGE_TOKEN (див. .env.example)")
        return Config(url, token, os.environ.get("ADSPOWER_API_URL", "http://local.adspower.net:50325").rstrip("/"),
                      os.environ.get("ADSPOWER_API_KEY", ""))
