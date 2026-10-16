from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

def _find_env() -> Path | None:
    """.env лежить у корені репозиторію; у контейнері змінні приходять із середовища."""
    for p in Path(__file__).resolve().parents:
        if (p / ".env").is_file():
            return p / ".env"
    return None



class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_env(), extra="ignore")

    app_env: str = "dev"
    app_tz: str = "Europe/Kyiv"
    secret_key: str
    session_ttl_hours: int = 12
    database_url: str
    cookie_secure: bool = False
    clover_spend_secret: str = ""
    bridge_token: str = ""
    fbm_api_url: str = "https://fbm-pay.com"
    fbm_api_key: str = ""


settings = Settings()
