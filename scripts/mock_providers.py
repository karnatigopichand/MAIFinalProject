"""Local, deterministic HTTP implementations of the demo payment and carrier APIs.

These endpoints are for local demonstrations only. They do not move money or
book real shipments. Run with: python3 scripts/mock_providers.py
"""
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class ProviderHandler(BaseHTTPRequestHandler):
    provider = ""

    def log_message(self, *_args):
        pass

    def respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            self.respond(200, {"service": self.provider, "status": "up"})
        else:
            self.respond(404, {"error": "not_found"})

    def do_POST(self):
        token_name = self.provider.replace("-", "_").upper() + "_TOKEN"
        expected = os.environ.get(token_name, "")
        if expected:
            supplied = self.headers.get("Authorization", "")
            candidate = supplied[7:] if supplied.startswith("Bearer ") else ""
            if not hmac.compare_digest(candidate, expected):
                return self.respond(401, {"error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                return self.respond(400, {"error": "invalid_body_size"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("object required")
            path = urlparse(self.path).path
            if self.provider == "payment-provider-api" and path == "/charges":
                return self.charge(payload)
            if self.provider == "carrier-provider-api" and path == "/shipments":
                return self.ship(payload)
            self.respond(404, {"error": "not_found"})
        except (ValueError, json.JSONDecodeError):
            self.respond(400, {"error": "invalid_request"})

    def charge(self, payload):
        amount, currency, token = payload.get("amount"), payload.get("currency"), payload.get("token")
        if type(amount) is not int or amount <= 0 or currency != "USD" or not isinstance(token, str) or not token:
            return self.respond(422, {"error": "invalid_charge"})
        # A reserved synthetic token makes the decline path reproducible.
        if token == "demo-decline":
            return self.respond(200, {"status": "declined"})
        digest = hashlib.sha256(token.encode()).hexdigest()[:12]
        self.respond(200, {"status": "authorized", "authorization_id": f"demo-auth-{digest}"})

    def ship(self, payload):
        reference, address = payload.get("reference"), payload.get("address")
        if not isinstance(reference, str) or not reference or not isinstance(address, str) or not address:
            return self.respond(422, {"error": "invalid_shipment"})
        digest = hashlib.sha256(reference.encode()).hexdigest()[:12].upper()
        self.respond(200, {"tracking_number": f"DEMO-{digest}"})


def serve(provider, port):
    handler = type(f"{provider.replace('-', '_')}Handler", (ProviderHandler,), {"provider": provider})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(json.dumps({"service": provider, "host": "127.0.0.1", "port": port, "status": "up"}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    from threading import Event, Thread

    for name, port in (("payment-provider-api", 9000), ("carrier-provider-api", 9001)):
        Thread(target=serve, args=(name, port), daemon=True).start()
    try:
        Event().wait()
    except KeyboardInterrupt:
        pass
