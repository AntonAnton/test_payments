from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import PaymentCreate


def test_payment_rejects_non_positive_amount():
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=Decimal("0"),
            currency="RUB",
            description="Order",
            webhook_url="https://example.com/hook",
        )


def test_payment_rejects_too_many_decimal_places():
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=Decimal("1.001"),
            currency="RUB",
            description="Order",
            webhook_url="https://example.com/hook",
        )
