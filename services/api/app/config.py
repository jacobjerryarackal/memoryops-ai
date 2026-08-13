import ssl
from typing import Optional, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database Configuration
    database_type: str = Field(default="memory")
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="postgres")
    postgres_user: str = Field(default="postgres")
    postgres_password: str = Field(default="postgres")
    
    # Connection Pool Configuration
    postgres_min_pool_size: int = Field(default=2)
    postgres_max_pool_size: int = Field(default=10)
    postgres_connection_timeout: float = Field(default=10.0)
    
    # TLS/SSL Configuration
    postgres_ssl: str = Field(default="prefer")  # disable, prefer, require, verify-ca, verify-full
    
    # Production-safety and defaults
    environment: str = Field(default="development")

    # JWT Configuration
    jwt_secret: str = Field(default="memoryops-jwt-secret-key-change-in-production")
    jwt_algorithms: list = Field(default=["HS256"])
    jwt_issuer: str = Field(default="memoryops-ai")
    jwt_audience: str = Field(default="memoryops-ai-clients")

    @field_validator("database_type")
    @classmethod
    def validate_database_type(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in ("memory", "postgres"):
            raise ValueError("DATABASE_TYPE must be either 'memory' or 'postgres'.")
        return v_clean

    @field_validator("postgres_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError("POSTGRES_PORT must be between 1 and 65535.")
        return v

    @field_validator("postgres_min_pool_size", "postgres_max_pool_size")
    @classmethod
    def validate_pool_sizes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Pool sizes must be positive integers.")
        return v

    @field_validator("postgres_connection_timeout")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("POSTGRES_CONNECTION_TIMEOUT must be a positive float.")
        return v

    @field_validator("postgres_ssl")
    @classmethod
    def validate_ssl(cls, v: str) -> str:
        v_clean = v.strip().lower()
        valid = ("disable", "prefer", "require", "verify-ca", "verify-full")
        if v_clean not in valid:
            raise ValueError(f"POSTGRES_SSL must be one of {valid}")
        return v_clean

    def model_post_init(self, __context) -> None:
        # Cross-field validations
        if self.database_type == "postgres":
            if self.postgres_min_pool_size > self.postgres_max_pool_size:
                raise ValueError("POSTGRES_MIN_POOL_SIZE cannot be greater than POSTGRES_MAX_POOL_SIZE.")
            
            # Enforce production safety constraints
            if self.environment.strip().lower() == "production":
                if self.postgres_ssl.strip().lower() in ("disable", "prefer"):
                    raise ValueError("Production safety violation: SSL/TLS must be 'require', 'verify-ca', or 'verify-full' in production.")
                if self.postgres_user == "postgres" or self.postgres_password == "postgres":
                    raise ValueError("Production safety violation: Default postgres user or password is not allowed in production.")


# Global instance instantiated on import to trigger fail-fast validation
settings = Settings()
