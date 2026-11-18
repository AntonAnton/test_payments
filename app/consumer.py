import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone

import httpx
from faststream import FastStream
from pydantic import BaseModel
from sqlalchemy import select

from app.broker import create_broker, declare_topology, exchange, queue
from app.config import settings
from app.db import session_factory
from app.models import Payment, PaymentStatus

log = logging.getLogger("consumer")

broker = create_broker()
app = FastStream(broker)


class NewPayment(BaseModel):
    payment_id: uuid.UUID


@app.on_startup
async def _topology() -> None:
    # DLQ must be bound before the subscriber starts consuming, otherwise early rejects are lost
    await broker.connect()
    await declare_topology(broker)


async def _load_pending(payment_id: uuid.UUID) -> bool:
    async with session_factory() as session:
        payment = await session.get(Payment, payment_id)
    if payment is None:
        log.warning("payment %s not found", payment_id)
        return False
    return payment.status == PaymentStatus.pending.value


async def process_payment(payment_id: uuid.UUID) -> Payment | None:
    """Emulate the gateway and persist the result.

    The slow gateway call happens outside any transaction, so no row lock or DB connection is held
    while waiting. The final write re-checks the status under a row lock, so duplicate deliveries
    cannot overwrite a finished payment.
    """
    if await _load_pending(payment_id):
        await asyncio.sleep(random.uniform(2, 5))
        outcome = PaymentStatus.succeeded if random.random() < 0.9 else PaymentStatus.failed
    else:
        outcome = None

    async with session_factory() as session, session.begin():
        payment = await session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
        if payment is not None and outcome and payment.status == PaymentStatus.pending.value:
            payment.status = outcome.value
            payment.processed_at = datetime.now(timezone.utc)
        return payment

async def send_webhook(payment: Payment) -> None:
    body = {
        "payment_id": str(payment.id),
        "status": payment.status,
        "amount": format(payment.amount, "f"),
        "currency": payment.currency,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }
    async with httpx.AsyncClient(timeout=settings.webhook_timeout) as client:
        response = await client.post(
            payment.webhook_url,
            json=body,
            headers={"Idempotency-Key": str(payment.id)},
        )
        response.raise_for_status()


@broker.subscriber(queue, exchange, retry=False)
async def handle_new_payment(msg: NewPayment) -> None:
    last_error: Exception | None = None
    for attempt in range(1, settings.max_attempts + 1):
        try:
            payment = await process_payment(msg.payment_id)
            if payment is not None:
                await send_webhook(payment)
            return
        except Exception as exc:
            last_error = exc
            log.warning("payment attempt %d/%d failed: %r", attempt, settings.max_attempts, exc)
            if attempt < settings.max_attempts:
                await asyncio.sleep(settings.retry_base_delay * 2 ** (attempt - 1))

    raise RuntimeError(
        f"payment processing failed after {settings.max_attempts} attempts"
    ) from last_error
