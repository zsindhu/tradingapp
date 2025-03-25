from pydantic_settings import BaseSettings
from typing import List, Optional, Dict, Any
import os

class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Premium Trader API"
    API_V1_STR: str = "/api/v1"
    BASE_URL: str = os.environ.get("BASE_URL", "http://localhost:8000")
    
    # Security settings
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "your-secret-key-for-development")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # CORS settings
    FRONTEND_URLS: List[str] = [
        "http://localhost:3000",
        "https://app.premiumtrader.com"
    ]
    
    # Database settings
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
    
    # Schwab OAuth settings
    SCHWAB_CLIENT_ID: str = os.environ.get("SCHWAB_CLIENT_ID", "")
    SCHWAB_CLIENT_SECRET: str = os.environ.get("SCHWAB_CLIENT_SECRET", "")
    SCHWAB_API_BASE_URL: str = "https://api.schwab.com/"
    
    # Development settings
    DEV_MODE: bool = os.environ.get("DEV_MODE", "False").lower() == "true"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
settings = Settings()