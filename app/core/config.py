from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EmlakAI Backend"
    app_version: str = "0.1.0"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/emlakai"
    redis_url: str = "redis://localhost:6379/0"

    # Provider configuration
    sahibinden_search_url: str = "https://www.sahibinden.com/satilik-daire"
    emlakjet_search_url: str = "https://www.emlakjet.com/projeler/"
    hepsiemlak_search_url: str = "https://www.hepsiemlak.com/istanbul-satilik"
    provider_request_timeout_seconds: int = 20
    provider_max_items: int = 20

    # Kaggle API credentials (for dataset import)
    kaggle_username: str = ""
    kaggle_key: str = ""

    # OpenStreetMap APIs
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    user_agent: str = "EmlakAI/1.0"

    # Guvenli varsayilan: seed startup'ta kapali gelir, sadece gerekiyorsa acilir.
    seed_on_startup: bool = False

    # Gemini AI configuration
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_timeout_seconds: int = 60

    # Logging configuration
    log_level: str = "INFO"
    # CORS configuration
    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    cors_allowed_credentials: bool = True
    cors_allowed_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    cors_allowed_headers: list[str] = ["*"]


settings = Settings()
