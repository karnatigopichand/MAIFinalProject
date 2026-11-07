"""Loopback demo UI and same-origin bridge to the local assessment and APIs."""
from __future__ import annotations

import json
import hmac
import os
import socket
import threading
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit

from .integrations.jira import JiraClient
from .workflow import AssessmentWorkflow, ticket_from_jira


SERVICE_URLS = {
    "commerce-checkout": "http://127.0.0.1:8000",
    "commerce-orders": "http://127.0.0.1:8001",
    "commerce-inventory": "http://127.0.0.1:8002",
    "commerce-payments": "http://127.0.0.1:8003",
    "commerce-shipping": "http://127.0.0.1:8004",
    "commerce-notifications": "http://127.0.0.1:8005",
    "payment-provider-api": "http://127.0.0.1:9000",
    "carrier-provider-api": "http://127.0.0.1:9001",
}
for _service_name in tuple(SERVICE_URLS):
    _env_name = "IMPACT_URL_" + _service_name.replace("-", "_").upper()
    SERVICE_URLS[_service_name] = os.environ.get(_env_name, SERVICE_URLS[_service_name]).rstrip("/")
ASSETS = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.css": "app.css",
    "/app.js": "app.js",
    "/vendor/react.production.min.js": "vendor/react.production.min.js",
    "/vendor/react-dom.production.min.js": "vendor/react-dom.production.min.js",
}


def _json_call(url, payload=None, timeout=2):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("COMMERCE_API_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=data, headers=headers,
                          method="GET" if data is None else "POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read()), response.status
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise RuntimeError(f"Upstream returned HTTP {status}") from None


def _broker_status():
    try:
        host = os.environ.get("IMPACT_BROKER_HOST", "127.0.0.1")
        port = int(os.environ.get("IMPACT_BROKER_PORT", "61613"))
        with socket.create_connection((host, port), timeout=1):
            return "reachable"
    except OSError:
        return "offline"


def build_status():
    services = []
    for name, base in SERVICE_URLS.items():
        try:
            body, _ = _json_call(f"{base}/health", timeout=1)
            services.append({"name": name, "status": body.get("status", "unknown"), "url": base})
        except Exception:
            services.append({"name": name, "status": "offline", "url": base})
    return {"services": services, "broker": _broker_status(),
            "note": "Service health is liveness only. Broker reachability does not prove workers are subscribed."}


def create_handler(workspace: Path, auth_token=None):
    static_dir = Path(__file__).parent / "ui"
    workflow = AssessmentWorkflow(workspace)
    run_lock = threading.Lock()
    rate_lock = threading.Lock()
    request_times = defaultdict(deque)

    class Handler(BaseHTTPRequestHandler):
        server_version = "ImpactDemoUI/1.0"

        def log_message(self, *_args):
            pass

        def send_json(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.security_headers()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def security_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none'; frame-ancestors 'none'")

        def authorized(self):
            if not auth_token:
                return True
            supplied = self.headers.get("Authorization", "")
            token = supplied[7:] if supplied.startswith("Bearer ") else ""
            if not hmac.compare_digest(token, auth_token):
                return False
            origin = self.headers.get("Origin")
            if origin:
                origin_host = urlsplit(origin).netloc
                if not origin_host or origin_host != self.headers.get("Host", ""):
                    return False
            return True

        def within_rate_limit(self):
            now = time.monotonic()
            key = self.client_address[0]
            with rate_lock:
                bucket = request_times[key]
                while bucket and now - bucket[0] > 60:
                    bucket.popleft()
                if len(bucket) >= 12:
                    return False
                bucket.append(now)
                return True

        def do_GET(self):
            if self.path == "/api/config":
                jira_keys = ("IMPACT_JIRA_BASE_URL", "IMPACT_JIRA_EMAIL", "IMPACT_JIRA_API_TOKEN")
                missing = [key for key in jira_keys if not os.environ.get(key)]
                return self.send_json(200, {"auth_required": bool(auth_token),
                                            "jira_configured": not missing,
                                            "jira_missing_settings": missing})
            if self.path.startswith("/api/") and not self.authorized():
                return self.send_json(401, {"error": "unauthorized"})
            if self.path == "/api/status":
                return self.send_json(200, build_status())
            if self.path.startswith("/api/order/"):
                order_id = self.path.removeprefix("/api/order/")
                if not order_id or "/" in order_id:
                    return self.send_json(400, {"error": "invalid_order_id"})
                result = {}
                for key, url in (("shipment", f"{SERVICE_URLS['commerce-shipping']}/shipments/{order_id}"),
                                 ("order_notification", f"{SERVICE_URLS['commerce-notifications']}/notifications/order:{order_id}"),
                                 ("shipment_notification", f"{SERVICE_URLS['commerce-notifications']}/notifications/shipment:{order_id}")):
                    try:
                        body, _ = _json_call(url, timeout=1)
                        result[key] = body
                    except Exception:
                        result[key] = None
                return self.send_json(200, result)
            asset = ASSETS.get(self.path.split("?", 1)[0])
            if not asset:
                return self.send_json(404, {"error": "not_found"})
            try:
                content = (static_dir / asset).read_bytes()
            except OSError:
                return self.send_json(500, {"error": "ui_asset_unavailable"})
            content_type = "text/html; charset=utf-8" if asset.endswith("html") else (
                "text/css; charset=utf-8" if asset.endswith("css") else "text/javascript; charset=utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.security_headers()
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            if not self.authorized():
                return self.send_json(401, {"error": "unauthorized"})
            if not self.within_rate_limit():
                return self.send_json(429, {"error": "rate_limit_exceeded", "detail": "Try again in one minute."})
            if self.path not in {"/api/assess", "/api/commerce-order", "/api/jira-issue", "/api/jira-search"}:
                return self.send_json(404, {"error": "not_found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 100_000:
                    return self.send_json(400, {"error": "invalid_body_size"})
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    return self.send_json(400, {"error": "json_object_required"})
                if self.path == "/api/assess":
                    return self.assess(payload)
                if self.path == "/api/jira-issue":
                    return self.fetch_jira_issue(payload)
                if self.path == "/api/jira-search":
                    return self.search_jira_issues(payload)
                return self.commerce_order(payload)
            except (ValueError, KeyError, TypeError) as exc:
                return self.send_json(400, {"error": "invalid_request", "detail": str(exc)[:160]})
            except RuntimeError as exc:
                return self.send_json(502, {"error": "upstream_failure", "detail": str(exc)})
            except Exception as exc:
                return self.send_json(500, {"error": "demo_request_failed", "type": type(exc).__name__})

        def assess(self, payload):
            summary = payload.get("summary", "")
            description = payload.get("description", "")
            criteria = payload.get("acceptance_criteria", [])
            if not isinstance(summary, str) or len(summary) > 300:
                return self.send_json(400, {"error": "summary_must_be_a_string_under_300_chars"})
            if not isinstance(description, str) or len(description) > 8000:
                return self.send_json(400, {"error": "description_must_be_a_string_under_8000_chars"})
            if not isinstance(criteria, list) or len(criteria) > 20 or any(not isinstance(x, str) for x in criteria):
                return self.send_json(400, {"error": "acceptance_criteria_must_be_a_list_of_strings"})
            ticket_id = payload.get("ticket_id", "DEMO-1")
            version = str(payload.get("ticket_version", "1"))
            if not isinstance(ticket_id, str) or not ticket_id.strip() or len(ticket_id) > 80:
                return self.send_json(400, {"error": "invalid_ticket_id"})
            ticket = {"ticket_id": ticket_id.strip(), "ticket_version": version,
                      "summary": summary, "description": description,
                      "acceptance_criteria": criteria}
            with run_lock:
                assessment = workflow.run(ticket)
            return self.send_json(200, assessment.to_dict())

        def fetch_jira_issue(self, payload):
            issue_key = payload.get("issue_key", "")
            if not isinstance(issue_key, str) or not issue_key.strip() or len(issue_key) > 80:
                return self.send_json(400, {"error": "invalid_issue_key"})
            jira_keys = ("IMPACT_JIRA_BASE_URL", "IMPACT_JIRA_EMAIL", "IMPACT_JIRA_API_TOKEN")
            missing = [key for key in jira_keys if not os.environ.get(key)]
            if missing:
                return self.send_json(503, {"error": "jira_not_configured",
                                            "detail": "Set these server environment variables: " + ", ".join(missing)})
            criteria_field = os.environ.get("IMPACT_JIRA_CRITERIA_FIELD", "customfield_10000")
            try:
                issue = JiraClient().get_issue(issue_key.strip(), criteria_field)
                ticket = ticket_from_jira(issue, criteria_field)
            except RuntimeError as exc:
                return self.send_json(502, {"error": "jira_fetch_failed", "detail": str(exc)})
            except Exception as exc:
                return self.send_json(502, {"error": "jira_fetch_failed",
                                            "detail": f"Jira request failed ({type(exc).__name__})"})
            if not ticket.get("summary"):
                return self.send_json(502, {"error": "jira_issue_invalid",
                                            "detail": "Jira returned an issue without a summary; check the issue key and read permission."})
            return self.send_json(200, ticket)

        def search_jira_issues(self, payload):
            query = payload.get("query", "")
            if not isinstance(query, str) or len(query.strip()) < 2 or len(query) > 80:
                return self.send_json(200, {"issues": []})
            jira_keys = ("IMPACT_JIRA_BASE_URL", "IMPACT_JIRA_EMAIL", "IMPACT_JIRA_API_TOKEN")
            missing = [key for key in jira_keys if not os.environ.get(key)]
            if missing:
                return self.send_json(503, {"error": "jira_not_configured",
                                            "detail": "Set these server environment variables: " + ", ".join(missing)})
            try:
                issues = JiraClient().search_issue_suggestions(
                    query.strip(), os.environ.get("JIRA_PROJECT_KEY"), limit=10)
            except RuntimeError as exc:
                return self.send_json(502, {"error": "jira_search_failed", "detail": str(exc)})
            except Exception as exc:
                return self.send_json(502, {"error": "jira_search_failed",
                                            "detail": f"Jira search failed ({type(exc).__name__})"})
            return self.send_json(200, {"issues": issues})

        def commerce_order(self, payload):
            sku = payload.get("sku", "book")
            quantity = payload.get("quantity", 1)
            total_cents = payload.get("total_cents", 2500)
            address = payload.get("delivery_address", "10 Main St")
            payment_token = payload.get("payment_token", "demo-token")
            if not isinstance(sku, str) or not sku or len(sku) > 80:
                return self.send_json(400, {"error": "invalid_sku"})
            if type(quantity) is not int or not 1 <= quantity <= 100:
                return self.send_json(400, {"error": "quantity_must_be_between_1_and_100"})
            if type(total_cents) is not int or total_cents <= 0:
                return self.send_json(400, {"error": "total_cents_must_be_positive"})
            if not isinstance(address, str) or not address.strip() or len(address) > 500:
                return self.send_json(400, {"error": "delivery_address_required"})
            if not isinstance(payment_token, str) or not payment_token or len(payment_token) > 120:
                return self.send_json(400, {"error": "payment_token_required"})
            order_id = f"ui-{uuid.uuid4().hex[:10]}"
            _json_call(f"{SERVICE_URLS['commerce-inventory']}/stock", {"sku": sku, "quantity": 100})
            result, _ = _json_call(f"{SERVICE_URLS['commerce-checkout']}/checkout", {
                "checkout_id": order_id,
                "cart": {"items": [{"sku": sku, "quantity": quantity}]},
                "total_cents": total_cents,
                "currency": "USD",
                "delivery": {"address": address.strip()},
                "payment_token": payment_token,
            }, timeout=10)
            return self.send_json(200, {"order_id": order_id, "checkout": result,
                                        "message": "Checkout accepted; shipment and notifications arrive asynchronously."})

    return Handler


def serve(workspace: Path, host=None, port=None):
    default_host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    listen_host = host or os.environ.get("IMPACT_UI_HOST", default_host)
    listen_port = int(port or os.environ.get("IMPACT_UI_PORT") or os.environ.get("PORT", "8088"))
    auth_token = os.environ.get("IMPACT_UI_TOKEN")
    if listen_host not in {"127.0.0.1", "localhost", "::1"} and not auth_token:
        raise RuntimeError("Set IMPACT_UI_TOKEN before binding the demo UI to a public interface")
    server = ThreadingHTTPServer((listen_host, listen_port), create_handler(workspace.resolve(), auth_token))
    print(json.dumps({"service": "impact-demo-ui", "url": f"http://{listen_host}:{listen_port}"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
