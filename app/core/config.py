from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Self

class Settings(BaseSettings):
    PROJECT_NAME: str = "Reazy API"
    API_V1_STR: str = "/api"
    
    # Database
    DATABASE_URL: str
    MIGRATION_DATABASE_URL: Optional[str] = None
    
    @field_validator("DATABASE_URL")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
    
    # Security
    SECRET_KEY: str = "your-secret-key-here" # Change in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days

    @field_validator("CORS_ORIGIN_URLS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str] | str:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    CORS_ORIGIN_URLS: list[str] | str = []

    # Extra
    PORT: int = 8000

    # AI
    GEMINI_API_KEY: Optional[str] = None
    AI_CACHE_ENABLED: bool = True
    
    # Ollama / Local AI
    AI_PROVIDER: str = "google" # 'google' or 'ollama'
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "deepseek-r1:latest"

    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
