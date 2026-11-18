import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Outbox, Payment
from app.schemas import PaymentCreate


class IdempotencyConflict(Exception):
    """The Idempotency-Key was already used with a different request body."""


def _matches(payment: Payment, data: PaymentCreate) -> bool:
    return (
        payment.amount == data.amount
        and payment.currency == data.currency.value
        and payment.description == data.description
        and payment.meta == data.metadata
        and payment.webhook_url == str(data.webhook_url)
    )


async def _find_by_key(session: AsyncSession, key: str) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.idempotency_key == key))


async def _replay(existing: Payment, data: PaymentCreate) -> Payment:
    if not _matches(existing, data):
        raise IdempotencyConflict(existing.idempotency_key)
    return existing


async def create_payment(session: AsyncSession, data: PaymentCreate, idempotency_key: str) -> Payment:
    """Create a payment and its outbox event atomically; replays return the original payment."""
    if existing := await _find_by_key(session, idempotency_key):
        return await _replay(existing, data)

    payment = Payment(
        id=uuid.uuid4(),
        amount=data.amount,
        currency=data.currency.value,
        description=data.description,
        meta=data.metadata,
        idempotency_key=idempotency_key,
        webhook_url=str(data.webhook_url),
    )
    session.add(payment)
    session.add(Outbox(event_type="payments.new", payload={"payment_id": str(payment.id)}))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _find_by_key(session, idempotency_key)
        if existing is None:
            raise
        return await _replay(existing, data)
    await session.refresh(payment)
    return payment
