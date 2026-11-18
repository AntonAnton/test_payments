from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings

ROUTING_KEY = "payments.new"

exchange = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
dlx = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

queue = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key=ROUTING_KEY,
    arguments={"x-dead-letter-exchange": "payments.dlx", "x-dead-letter-routing-key": "payments.dlq"},
)
dlq = RabbitQueue("payments.dlq", durable=True, routing_key="payments.dlq")


def create_broker() -> RabbitBroker:
    return RabbitBroker(settings.rabbitmq_url)


async def declare_topology(broker: RabbitBroker) -> None:
    ex = await broker.declare_exchange(exchange)
    dlx_ex = await broker.declare_exchange(dlx)
    dlq_q = await broker.declare_queue(dlq)
    await dlq_q.bind(dlx_ex, routing_key="payments.dlq")
    q = await broker.declare_queue(queue)
    await q.bind(ex, routing_key=ROUTING_KEY)
