"""Implemented business behavior; dependency contracts live in contracts.json."""
from .runtime import Database, HTTPClient, ActiveMQEvents, load_config, publish_pending

class Service:
    def __init__(self, db=None, http=None, events=None):
        config = load_config() if db is None or http is None or events is None else None
        self.db = db if db is not None else Database(config['database']['path'])
        self.http = http if http is not None else HTTPClient(config)
        self.events = events if events is not None else ActiveMQEvents(config)

    def create_order(self, request):
        key = request["order_id"]
        previous = self.db.get("orders", key)
        if previous:
            publish_pending(self.db, self.events, "order.confirmed.v1", {"event_id":f"order:{key}",**previous})
            return previous
        if not request["items"] or type(request["total_cents"]) is not int or request["total_cents"] <= 0:
            raise ValueError("Items and positive integer total_cents required")
        # HTTP dependency: commerce-inventory POST /reservations.
        self.http.post("commerce-inventory", "/reservations", {"order_id":key,"items":request["items"]})
        # HTTP dependency: commerce-payments POST /authorizations.
        self.http.post("commerce-payments", "/authorizations", {
            "order_id":key,"amount_cents":request["total_cents"],
            "currency":request["currency"],"payment_token":request["payment_token"]})
        result = {"order_id":key,"status":"confirmed","delivery_address":request["delivery_address"]}
        self.db.put("orders", key, result)
        # MQ dependency: commerce-shipping and commerce-notifications consume this contract.
        publish_pending(self.db, self.events, "order.confirmed.v1", {"event_id":f"order:{key}",**result})
        return result
