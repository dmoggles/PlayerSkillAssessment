from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    public_base_url: str = "http://localhost:8080"
    secure_cookies: bool = False
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "assessment@localhost"
    session_days: int = 7
    app_version: str = "local"
    cleanup_interval_hours: float = 6
    api_docs_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
