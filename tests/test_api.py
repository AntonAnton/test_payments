import uuid
from decimal import Decimal

import pytest

from app import services
from app.models import Outbox, Payment
from app.schemas import PaymentCreate


class FakeSession:
    def __init__(self, existing: Payment | None = None):
        self.existing = existing
        self.added = []

    async def scalar(self, statement):
        return self.existing

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        return None

    async def refresh(self, payment):
        payment.created_at = object()


@pytest.mark.asyncio
async def test_create_payment_adds_payment_and_outbox_together():
    session = FakeSession()
    body = PaymentCreate(
        amount=Decimal("100.50"),
        currency="RUB",
        description="Order",
        webhook_url="https://example.com/hook",
    )

    payment = await services.create_payment(session, body, "order-1")

    assert payment is session.added[0]
    assert isinstance(payment, Payment)
    assert isinstance(session.added[1], Outbox)
    assert session.added[1].payload == {"payment_id": str(payment.id)}


@pytest.mark.asyncio
async def test_create_payment_reuses_existing_idempotency_key():
    existing = Payment(
        id=uuid.uuid4(),
        idempotency_key="order-1",
        amount=Decimal("100.50"),
        currency="RUB",
        description="Order",
        meta={},
        webhook_url="https://example.com/hook",
    )
    session = FakeSession(existing)
    body = PaymentCreate(
        amount=Decimal("100.50"),
        currency="RUB",
        description="Order",
        webhook_url="https://example.com/hook",
    )

    payment = await services.create_payment(session, body, "order-1")

    assert payment is existing
    assert session.added == []


@pytest.mark.asyncio
async def test_create_payment_conflicts_on_different_body():
    existing = Payment(
        id=uuid.uuid4(),
        idempotency_key="order-1",
        amount=Decimal("1.00"),
        currency="RUB",
        description="Order",
        meta={},
        webhook_url="https://example.com/hook",
    )
    body = PaymentCreate(
        amount=Decimal("100.50"),
        currency="RUB",
        description="Order",
        webhook_url="https://example.com/hook",
    )

    with pytest.raises(services.IdempotencyConflict):
        await services.create_payment(FakeSession(existing), body, "order-1")