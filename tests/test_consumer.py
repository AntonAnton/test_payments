import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import consumer


@pytest.mark.asyncio
async def test_handler_retries_then_succeeds(monkeypatch):
    attempts = 0
    delays = []

    async def process_payment(payment_id):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("temporary failure")
        return None

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(consumer, "process_payment", process_payment)
    monkeypatch.setattr(consumer.asyncio, "sleep", sleep)

    await consumer.handle_new_payment(consumer.NewPayment(payment_id=uuid.uuid4()))

    assert attempts == 3
    assert delays == [consumer.settings.retry_base_delay, consumer.settings.retry_base_delay * 2]


@pytest.mark.asyncio
async def test_handler_raises_after_retry_limit(monkeypatch):
    async def process_payment(payment_id):
        raise OSError("persistent failure")

    async def sleep(delay):
        return None

    monkeypatch.setattr(consumer, "process_payment", process_payment)
    monkeypatch.setattr(consumer.asyncio, "sleep", sleep)

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        await consumer.handle_new_payment(consumer.NewPayment(payment_id=uuid.uuid4()))


@pytest.mark.asyncio
async def test_webhook_uses_payment_id_as_idempotency_key(monkeypatch):
    request = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            request.update(url=url, **kwargs)
            return SimpleNamespace(raise_for_status=lambda: None)

    payment = SimpleNamespace(
        id=uuid.uuid4(),
        status="succeeded",
        amount=Decimal("100.50"),
        currency="RUB",
        processed_at=None,
        webhook_url="https://example.com/hook",
    )
    monkeypatch.setattr(consumer.httpx, "AsyncClient", lambda **kwargs: Client())

    await consumer.send_webhook(payment)

    assert request["headers"]["Idempotency-Key"] == str(payment.id)
    assert request["url"] == payment.webhook_url
