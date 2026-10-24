"""Implemented business behavior; dependency contracts live in contracts.json."""
from .runtime import Database, HTTPClient, ActiveMQEvents, load_config

class Service:
    def __init__(self, db=None, http=None, events=None):
        config = load_config() if db is None or http is None or events is None else None
        self.db = db if db is not None else Database(config['database']['path'])
        self.http = http if http is not None else HTTPClient(config)
        self.events = events if events is not None else ActiveMQEvents(config)

    def checkout(self, request):
        key = request["checkout_id"]
        previous = self.db.get("checkouts", key)
        if previous:
            return previous
        items = request["cart"]["items"]
        if not items:
            raise ValueError("Empty cart")
        # HTTP dependency: commerce-orders POST /orders.
        result = self.http.post("commerce-orders", "/orders", {
            "order_id":key, "items":items, "total_cents":request["total_cents"],
            "currency":request.get("currency","USD"),
            "delivery_address":request["delivery"]["address"],
            "payment_token":request["payment_token"]})
        self.db.put("checkouts", key, result)
        return result
