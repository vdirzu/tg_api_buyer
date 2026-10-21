from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bot_token: SecretStr = SecretStr("")
    admin_ids: list[int] = []
    database_url: str = "postgresql+asyncpg://marketplace:marketplace@localhost/marketplace"
    key_hmac_secret: SecretStr = Field(min_length=1)
    payment_encryption_key: SecretStr = Field(min_length=1)
    csv_path: Path = Path("data/keys.csv")
    exchange_rate_url: str = "https://open.er-api.com/v6/latest/USD"
    exchange_rate_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    submission_interval_seconds: int = Field(default=3, ge=0)

    @field_validator("key_hmac_secret")
    @classmethod
    def strong_hmac(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("KEY_HMAC_SECRET must contain at least 32 characters")
        return value

    @field_validator("payment_encryption_key")
    @classmethod
    def fernet_key(cls, value: SecretStr) -> SecretStr:
        from cryptography.fernet import Fernet

        Fernet(value.get_secret_value().encode())
        return value
