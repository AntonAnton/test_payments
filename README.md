# Async payments processing service

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + RabbitMQ (FastStream) + Alembic.

## Run

```bash
cp .env.example .env
docker compose up --build
```

Set `WEB_CONCURRENCY` in `.env` to control the number of API workers; it defaults to `1`.
Set `API_PORT` if host port `8000` is already occupied.
Dependencies are locked in `uv.lock`. For local development, run `uv sync`, then `uv run pytest`.

API: http://localhost:8000 (docs at `/docs`), RabbitMQ UI: http://localhost:15672 (guest/guest).
All endpoints require header `X-API-Key: secret-api-key` (env `API_KEY`).

## Examples

```bash
curl -X POST localhost:8000/api/v1/payments \
  -H "X-API-Key: secret-api-key" -H "Idempotency-Key: order-1" -H "Content-Type: application/json" \
  -d '{"amount":"100.50","currency":"RUB","description":"Order 1","metadata":{"order":1},"webhook_url":"https://webhook.site/your-id"}'
# 202 {"payment_id":"...","status":"pending","created_at":"..."}

curl localhost:8000/api/v1/payments/<payment_id> -H "X-API-Key: secret-api-key"
```

Repeating the POST with the same `Idempotency-Key` and payload returns the original payment.
Reusing the key with a different payload returns `409 Conflict`.

## Design

- **Outbox**: the API inserts the payment and an `outbox` row in one transaction. A relay task (inside the api process) polls
  unpublished rows (`FOR UPDATE SKIP LOCKED`), publishes them to exchange `payments` (routing key `payments.new`) and marks
  them published only after the broker confirmed. Delivery is at-least-once.
- **Consumer** (`app/consumer.py`, single handler): takes the message, emulates the gateway (2–5 s, 90% succeeded / 10% failed),
  updates the status, sends the webhook. Already processed payments are not reprocessed (idempotent on redelivery).
- **Retry**: payment processing and webhook delivery are attempted 3 times with exponential backoff (1s, then 2s by default).
- **DLQ**: if all attempts fail, the message is rejected and dead-lettered via `payments.dlx` into `payments.dlq`.
- Migrations run once in the `migrate` one-shot service before API and consumer startup.

Webhook payload: `{"payment_id","status","amount","currency","processed_at"}`. Each delivery uses
`Idempotency-Key: <payment_id>` so receivers can deduplicate at-least-once delivery.
