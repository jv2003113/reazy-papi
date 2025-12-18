from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Reazy API"
    API_V1_STR: str = "/api"
    
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str = "your-secret-key-here" # Change in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000", 
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:4000", # Node API port just in case
    ]

    # Extra
    PORT: int = 8000
    CLIENT_URL: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
