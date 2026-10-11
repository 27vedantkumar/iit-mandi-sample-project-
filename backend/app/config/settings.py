import os
import secrets
import logging
from typing import List
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("edupath.config")

# Look for .env in current directory, project root, and backend directory
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, "../../../"))
_backend_root = os.path.abspath(os.path.join(_current_dir, "../../"))
_env_candidates = [
    os.path.join(os.getcwd(), ".env"),
    os.path.join(_project_root, ".env"),
    os.path.join(_backend_root, ".env"),
]
_env_file = next((f for f in _env_candidates if os.path.exists(f)), ".env")

class Settings(BaseSettings):
    PROJECT_NAME: str = "EduPath AI — Multimodal Adaptive Learning Companion"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Security & Tokens (Loaded from .env / environment)
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./edupath_multimodal.db"
    
    # Storage & Vectors
    STORAGE_PATH: str = "./uploads"
    VECTOR_STORE_PATH: str = "./vector_store"
    
    # AI Providers
    DEFAULT_AI_PROVIDER: str = "auto"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    
    # RAG & Grounding Gate
    RAG_SIMILARITY_THRESHOLD: float = 0.68
    GROUNDING_CONFIDENCE_THRESHOLD: float = 0.75
    MAX_CONTEXT_CHUNKS: int = 6
    ENABLE_HYBRID_BM25: bool = True
    
    # Code Execution Sandbox Limits & Isolation
    CODE_RUN_TIMEOUT_SECONDS: int = 5
    MAX_CODE_LENGTH: int = 10000
    MAX_OUTPUT_BYTES: int = 50000
    SANDBOX_MEMORY_LIMIT_MB: int = 256
    SANDBOX_CPU_QUOTA: float = 0.5
    USE_DOCKER_SANDBOX: bool = True
    DOCKER_PYTHON_IMAGE: str = "edupath-sandbox:latest"
    DOCKER_PYTHON_FALLBACK_IMAGE: str = "python:3.11-alpine"
    DOCKER_NODE_IMAGE: str = "node:20-alpine"
    
    # Server & Networking (Strict local frontend URLs, NO wildcard '*')
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        default_origins = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:3000"]
        if not self.CORS_ORIGINS:
            return default_origins
        # Strict parsing: filter out wildcard '*' to prevent insecure credential exposure
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip() and origin.strip() != "*"]
        return origins if origins else default_origins

    @model_validator(mode="after")
    def validate_security_settings(self):
        if not self.SECRET_KEY:
            if self.ENVIRONMENT.lower() in ["production", "prod"]:
                raise ValueError("CRITICAL SECURITY ERROR: SECRET_KEY environment variable is mandatory in production!")
            # In development mode, auto-generate a secure key and warn
            self.SECRET_KEY = secrets.token_hex(32)
            logger.warning("No SECRET_KEY found in .env / environment. Generated a temporary random key for development session.")
        return self

    model_config = SettingsConfigDict(
        env_file=_env_file,
        extra="ignore"
    )

settings = Settings()

