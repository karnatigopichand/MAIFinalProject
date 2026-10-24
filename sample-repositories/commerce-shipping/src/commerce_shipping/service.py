"""Implemented business behavior; dependency contracts live in contracts.json."""
from .runtime import Database, HTTPClient, ActiveMQEvents, load_config, publish_pending

class Service:
    def __init__(self, db=None, http=None, events=None):
        config = load_config() if db is None or http is None or events is None else None
        self.db = db if db is not None else Database(config['database']['path'])
        self.http = http if http is not None else HTTPClient(config)
        self.events = events if events is not None else ActiveMQEvents(config)

    def consume(self, topic, event):
        if topic != "order.confirmed.v1":
            raise ValueError("Unsupported topic")
        key = event["order_id"]
        previous = self.db.get("shipments",key)
        if previous:
            publish_pending(self.db, self.events, "shipment.created.v1", {"event_id":f"shipment:{key}",**previous})
            return previous
        # MQ input: order.confirmed.v1 from commerce-orders.
        # External HTTP dependency: carrier-provider-api POST /shipments.
        response = self.http.post("carrier-provider-api","/shipments", {
            "reference":key,"address":event["delivery_address"]})
        result = {"order_id":key,"tracking_number":response["tracking_number"]}
        self.db.put("shipments",key,result)
        # MQ output consumed by commerce-notifications.
        publish_pending(self.db, self.events, "shipment.created.v1", {"event_id":f"shipment:{key}",**result})
        return result
