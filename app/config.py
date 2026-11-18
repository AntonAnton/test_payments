from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    api_key: str = "secret-api-key"
    max_attempts: int = Field(default=3, ge=1)
    retry_base_delay: float = Field(default=1.0, gt=0)
    outbox_poll_interval: float = Field(default=0.5, gt=0)
    webhook_timeout: float = Field(default=5.0, gt=0)


settings = Settings()
