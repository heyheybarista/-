from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    public_base_url: str = "http://localhost:8000"
    pipeline_token: str = "change-me"
    secret_key: str = "change-me"
    database_path: str = "./data/app.db"

    model_config = dict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
