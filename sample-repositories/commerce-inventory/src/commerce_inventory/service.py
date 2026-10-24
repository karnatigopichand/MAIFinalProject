"""Implemented business behavior; dependency contracts live in contracts.json."""
from .runtime import Database, HTTPClient, ActiveMQEvents, load_config

class Service:
    def __init__(self, db=None, http=None, events=None):
        config = load_config() if db is None or http is None or events is None else None
        self.db = db if db is not None else Database(config['database']['path'])
        self.http = http if http is not None else HTTPClient(config)
        self.events = events if events is not None else ActiveMQEvents(config)

    def seed_stock(self, sku, quantity):
        if type(quantity) is not int or quantity < 0:
            raise ValueError("Invalid stock")
        self.db.put("stock", sku, {"quantity":quantity})

    def reserve(self, request):
        key = request["order_id"]
        previous = self.db.get("reservations", key)
        if previous:
            return previous
        quantities = {}
        for item in request["items"]:
            quantity = item["quantity"]
            if type(quantity) is not int or quantity <= 0:
                raise ValueError("Positive integer quantity required")
            quantities[item["sku"]] = quantities.get(item["sku"],0) + quantity
        if not quantities:
            raise ValueError("No items")
        for sku, quantity in quantities.items():
            if (self.db.get("stock",sku) or {"quantity":0})["quantity"] < quantity:
                raise ValueError(f"Insufficient stock: {sku}")
        for sku, quantity in quantities.items():
            current = self.db.get("stock",sku)["quantity"]
            self.db.put("stock",sku,{"quantity":current-quantity})
        result = {"order_id":key,"status":"reserved","items":quantities}
        self.db.put("reservations",key,result)
        return result
