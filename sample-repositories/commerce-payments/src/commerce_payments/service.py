"""Implemented business behavior; dependency contracts live in contracts.json."""
from .runtime import Database, HTTPClient, ActiveMQEvents, load_config

class Service:
    def __init__(self, db=None, http=None, events=None):
        config = load_config() if db is None or http is None or events is None else None
        self.db = db if db is not None else Database(config['database']['path'])
        self.http = http if http is not None else HTTPClient(config)
        self.events = events if events is not None else ActiveMQEvents(config)

    def authorize(self, request):
        key = request["order_id"]
        previous = self.db.get("authorizations",key)
        if previous:
            return previous
        if type(request["amount_cents"]) is not int or request["amount_cents"] <= 0:
            raise ValueError("Positive integer amount required")
        if request["currency"] != "USD":
            raise ValueError("Only USD supported")
        # External HTTP API; token never persisted in the application database.
        response = self.http.post("payment-provider-api","/charges", {
            "amount":request["amount_cents"],"currency":request["currency"],"token":request["payment_token"]})
        if response["status"] != "authorized":
            raise ValueError("Payment declined")
        result = {"order_id":key,"authorization_id":response["authorization_id"],"status":"authorized"}
        self.db.put("authorizations",key,result)
        return result
