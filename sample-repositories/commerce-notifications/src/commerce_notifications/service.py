"""Implemented business behavior; dependency contracts live in contracts.json."""
from .runtime import Database, HTTPClient, ActiveMQEvents, load_config

class Service:
    def __init__(self, db=None, http=None, events=None):
        config = load_config() if db is None or http is None or events is None else None
        self.db = db if db is not None else Database(config['database']['path'])
        self.http = http if http is not None else HTTPClient(config)
        self.events = events if events is not None else ActiveMQEvents(config)

    def consume(self, topic, event):
        if topic not in ("order.confirmed.v1","shipment.created.v1"):
            raise ValueError("Unsupported topic")
        key = event["event_id"]
        previous = self.db.get("outbox",key)
        if previous:
            return previous
        # MQ dependencies: orders publishes confirmation; shipping publishes tracking.
        if topic == "order.confirmed.v1":
            body = f"Order {event['order_id']} confirmed"
        else:
            body = f"Order {event['order_id']} shipped: {event['tracking_number']}"
        result = {"event_id":key,"topic":topic,"body":body}
        self.db.put("outbox",key,result)
        return result
