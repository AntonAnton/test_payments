import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, AnyHttpUrl, BaseModel, ConfigDict, Field, field_serializer

from app.models import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str = Field(min_length=1, max_length=1000)
    metadata: dict = Field(default_factory=dict)
    webhook_url: AnyHttpUrl


class PaymentCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: uuid.UUID = Field(validation_alias="id")
    status: PaymentStatus
    created_at: datetime


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: uuid.UUID = Field(validation_alias="id")
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict = Field(validation_alias=AliasChoices("meta", "metadata"))
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @field_serializer("amount")
    def _amount(self, v: Decimal) -> str:
        return format(v, "f")
