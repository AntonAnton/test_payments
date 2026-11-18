import asyncio
import logging
from datetime import datetime, timezone

from faststream.rabbit import RabbitBroker
from sqlalchemy import select

from app.broker import ROUTING_KEY, exchange
from app.config import settings
from app.db import session_factory
from app.models import Outbox

log = logging.getLogger("outbox-relay")


async def publish_pending(broker: RabbitBroker, batch: int = 50) -> int:
    async with session_factory() as session, session.begin():
        rows = (
            await session.scalars(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.id)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            await broker.publish(
                row.payload,
                exchange=exchange,
                routing_key=ROUTING_KEY,
                message_id=str(row.id),
                persist=True,
                timeout=10,
            )
            row.published_at = datetime.now(timezone.utc)
        return len(rows)


async def run_relay(broker: RabbitBroker) -> None:
    while True:
        try:
            if await publish_pending(broker):
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("outbox publish failed, will retry")
        await asyncio.sleep(settings.outbox_poll_interval)
