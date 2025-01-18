import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from pydantic import field_validator, HttpUrl, Field, ValidationInfo
from pydantic_settings import BaseSettings
from typing import Dict, Optional
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

def load_environment():
    try:
        env_path = BASE_DIR / '.env'
        if not env_path.exists():
            logging.warning(f".env file not found at {env_path}, using defaults")
            return
            
        load_dotenv(env_path)
        logging.info("Environment variables loaded successfully")
        
    except Exception as e:
        logging.error(f"Error loading .env file: {str(e)}")
        logging.warning("Using default configuration values")
        
load_environment()

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = os.path.join(BASE_DIR, "logs", "app.log")

os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

CHAT_HISTORY_WIDTH = "20%"
MAIN_PANEL_WIDTH = "80%"

SEARCH_TYPES = {
    "SUMMARIES": "Get high-level overview of code",
    "INSIGHTS": "Extract key implementation details", 
    "CHUNKS": "Retrieve relevant code segments",
    "COMPLETION": "Generate contextual responses"
}

class RetryConfig(BaseSettings):
    max_retries: int = 3
    retry_delay: float = 0.5
    retry_backoff: float = 2.0
    retry_max_delay: float = 10.0

class TimeoutConfig(BaseSettings):
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    pool_timeout: float = 30.0

class PaginationConfig(BaseSettings):
    chat_history_page_size: int = 50
    max_history_pages: int = 100
    default_page: int = 1

class Settings(BaseSettings):
    API_BASE_URL: HttpUrl = Field(
        ...,
        description="Base URL for the API",
        example="http://localhost:8000/api/v1"
    )
    DATABASE_PATH: Path = Field(
        default=Path("database/chat_history.db"),
        description="Path to SQLite database file"
    )
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level"
    )
    MAX_DB_CONNECTIONS: int = 5
    DB_TIMEOUT: int = 30

    MAX_MESSAGE_LENGTH: int = Field(
        default=10000,
        description="Maximum message length"
    )

    MAX_BATCH_SIZE: int = Field(
        default=100,
        description="Maximum batch operation size"
    )

    CLEANUP_INTERVAL: int = Field(
        default=3600,
        description="Cleanup interval in seconds"
    )

    LOG_FILE: Path = Field(
        default=Path(BASE_DIR) / "logs" / "app.log",
        description="Path to log file"
    )
    
    retry: RetryConfig = RetryConfig()
    timeout: TimeoutConfig = TimeoutConfig()
    pagination: PaginationConfig = PaginationConfig()
    
    @field_validator("API_BASE_URL")
    def validate_api_url(cls, v, info: ValidationInfo):
        if not v:
            raise ValueError("API_BASE_URL is required")
        parsed = urlparse(str(v))
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("API_BASE_URL must be a valid HTTP(S) URL")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("API_BASE_URL must use HTTP(S) protocol")
        return v

    @field_validator("LOG_LEVEL")
    def validate_log_level(cls, v, info: ValidationInfo):
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {', '.join(valid_levels)}")
        return v

    @field_validator("MAX_DB_CONNECTIONS")
    def validate_max_connections(cls, v, info: ValidationInfo):
        if v < 1:
            raise ValueError("MAX_DB_CONNECTIONS must be positive")
        return v

    @field_validator("DB_TIMEOUT")
    def validate_timeout(cls, v, info: ValidationInfo):
        if v < 0:
            raise ValueError("DB_TIMEOUT must be non-negative")
        return v

    @field_validator("DATABASE_PATH")
    def validate_database_path(cls, v, info: ValidationInfo):
        path = Path(v)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        return path

    @field_validator("*")
    def validate_not_none(cls, v, info: ValidationInfo):
        if v is None and not info.field.allow_none:
            raise ValueError(f"{info.field.name} cannot be None")
        return v
    
    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        validate_default = True

settings = Settings()