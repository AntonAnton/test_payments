import asyncio
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import services
from app.broker import create_broker, declare_topology
from app.config import settings
from app.db import session_factory
from app.models import Payment
from app.relay import run_relay
from app.schemas import PaymentCreate, PaymentCreated, PaymentOut
from app.services import IdempotencyConflict


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-API-Key")


async def get_session():
    async with session_factory() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    broker = create_broker()
    await broker.start()
    await declare_topology(broker)
    task = asyncio.create_task(run_relay(broker))
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await broker.close()


app = FastAPI(title="Payments service", dependencies=[Depends(require_api_key)], lifespan=lifespan)


@app.post(
    "/api/v1/payments",
    response_model=PaymentCreated,
    responses={status.HTTP_409_CONFLICT: {"description": "Idempotency key conflict"}},
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_payment(
    body: PaymentCreate,
    idempotency_key: str = Header(min_length=1, max_length=255),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await services.create_payment(session, body, idempotency_key)
    except IdempotencyConflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency-Key was already used with a different request",
        ) from None


@app.get("/api/v1/payments/{payment_id}", response_model=PaymentOut)
async def get_payment(payment_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment
