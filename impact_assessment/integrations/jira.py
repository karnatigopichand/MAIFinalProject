"""Jira Cloud webhook and retryable comment delivery adapter (stdlib only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request

from ..workflow import AssessmentWorkflow, ticket_from_jira


def _plain(value):
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), list):
            return " ".join(_plain(part) for part in value["content"])
        return " ".join(_plain(part) for part in value.values())
    if isinstance(value, list):
        return " ".join(_plain(part) for part in value)
    return "" if value is None else str(value)


class JiraClient:
    def __init__(self, base_url=None, email=None, token=None):
        self.base_url = (base_url or os.environ["IMPACT_JIRA_BASE_URL"]).rstrip("/")
        self.email = email or os.environ["IMPACT_JIRA_EMAIL"]
        self.token = token or os.environ["IMPACT_JIRA_API_TOKEN"]

    def _call(self, method, path, payload=None):
        url = self.base_url + path
        auth = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
        data = None if payload is None else json.dumps(payload).encode()
        req = request.Request(url, data=data, method=method, headers={
            "Authorization": f"Basic {auth}", "Accept": "application/json",
            "Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=15) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            # Do not preserve Jira response bodies; they may contain ticket data.
            status = exc.code
            exc.close()
            raise RuntimeError(f"Jira API returned HTTP {status}") from None

    def get_issue(self, issue_key, criteria_field):
        fields = ["summary", "description", "updated", "status", criteria_field]
        query = parse.urlencode({"fields": ",".join(fields)})
        return self._call("GET", f"/rest/api/3/issue/{parse.quote(issue_key, safe='')}?{query}")

    def search_issue_suggestions(self, query, project_key=None, limit=10):
        """Return Jira issue-picker matches for the configured demo stories."""
        current_jql = 'labels = "impact-assessment-sample"'
        if project_key and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,19}", project_key):
            current_jql = f'project = "{project_key}" AND {current_jql}'
        params = parse.urlencode({"query": query, "currentJQL": current_jql})
        response = self._call("GET", f"/rest/api/3/issue/picker?{params}")
        suggestions, seen = [], set()
        for section in response.get("sections", []):
            if section.get("label") != "Current Search":
                continue
            for issue in section.get("issues", []):
                key = issue.get("key")
                if not isinstance(key, str) or key in seen:
                    continue
                seen.add(key)
                suggestions.append({"key": key, "summary": issue.get("summaryText") or issue.get("summary") or ""})
                if len(suggestions) >= limit:
                    return suggestions
        return suggestions

    def has_run_comment(self, issue_key, run_id):
        marker = f"Impact assessment run: {run_id}"
        start = 0
        while True:
            page = self._call("GET", f"/rest/api/3/issue/{parse.quote(issue_key, safe='')}/comment?startAt={start}&maxResults=100")
            comments = page.get("comments", [])
            if any(marker in _plain(comment.get("body", "")) for comment in comments):
                return True
            start += len(comments)
            if not comments or start >= page.get("total", 0):
                return False

    def post_report(self, issue_key, run_id, report):
        if self.has_run_comment(issue_key, run_id):
            return "duplicate_skipped"
        marker = f"Impact assessment run: {run_id}"
        text = report[:28000]
        if len(report) > len(text):
            text += "\n\n[Report shortened in Jira. Full report is persisted with this run.]"
        body = {"version": 1, "type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": marker}]},
            *self._markdown_blocks(text),
        ]}
        self._call("POST", f"/rest/api/3/issue/{parse.quote(issue_key, safe='')}/comment", {"body": body})
        return "posted"

    @staticmethod
    def _markdown_blocks(markdown):
        blocks = []
        for line in markdown.splitlines():
            if not line.strip() or line.startswith("|---") or line.startswith("|---|"):
                continue
            if line.startswith("# "):
                blocks.append({"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": line[2:]}]})
            elif line.startswith("## "):
                blocks.append({"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": line[3:]}]})
            else:
                plain = re.sub(r"[`*_]", "", line)
                plain = re.sub(r"^\|\s*|\s*\|$", "", plain)
                if plain:
                    blocks.append({"type": "paragraph", "content": [{"type": "text", "text": plain}]})
        return blocks


def _run_id(ticket, snapshot_id):
    import hashlib
    material = f"{ticket['ticket_id']}\0{ticket['ticket_version']}\0{snapshot_id}"
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def process_transition(payload, workflow: AssessmentWorkflow, jira: JiraClient,
                       ready_status="Ready for Impact Analysis", criteria_field="customfield_10000"):
    issue_key = payload.get("issue", {}).get("key")
    if not issue_key:
        return {"status": "ignored", "reason": "issue key missing"}
    items = payload.get("changelog", {}).get("items", [])
    transition = payload.get("transition", {})
    transitioned = ((transition.get("to_status") or "").lower() == ready_status.lower()
                    or any(item.get("field", "").lower() == "status"
                           and (item.get("toString") or "").lower() == ready_status.lower()
                           for item in items))
    if not transitioned:
        return {"status": "ignored", "reason": "target status transition not present"}

    # Always fetch current fields from Jira; webhook descriptions are not trusted as complete.
    issue = jira.get_issue(issue_key, criteria_field)
    ticket = ticket_from_jira(issue, criteria_field)
    if not ticket["ticket_version"]:
        return {"status": "rejected", "reason": "issue version missing"}
    snapshot = workflow.store.build_snapshot()
    run_id = _run_id(ticket, snapshot["snapshot_id"])
    run_dir = workflow.state_dir / "runs" / run_id
    result_path = run_dir / "assessment.json"
    if result_path.exists():
        report = (run_dir / "report.md").read_text(encoding="utf-8")
        result = "reused"
    else:
        assessment = workflow.run(ticket, rebuild_snapshot=False)
        report = assessment.report_markdown
        result = "assessed"
    try:
        delivery = jira.post_report(issue_key, run_id, report)
        record = {"issue_key": issue_key, "run_id": run_id, "status": delivery,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        # Keep the assessment successful and make delivery independently retryable.
        delivery = "failed"
        record = {"issue_key": issue_key, "run_id": run_id, "status": delivery,
                  "error_type": type(exc).__name__, "updated_at": datetime.now(timezone.utc).isoformat()}
    (run_dir / "delivery.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {"status": result, "delivery": delivery, "run_id": run_id,
            **({"error_type": record["error_type"]} if delivery == "failed" else {})}


def retry_delivery(workspace: Path, run_id: str, jira: JiraClient):
    run_dir = workspace / ".impact_assessment" / "runs" / run_id
    report_path = run_dir / "report.md"
    assessment_path = run_dir / "assessment.json"
    if not report_path.exists() or not assessment_path.exists():
        raise FileNotFoundError(f"No saved assessment for run {run_id}")
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    issue_key = assessment["context"]["ticket_id"]
    status = jira.post_report(issue_key, run_id, report_path.read_text(encoding="utf-8"))
    record = {"issue_key": issue_key, "run_id": run_id, "status": status,
              "updated_at": datetime.now(timezone.utc).isoformat()}
    (run_dir / "delivery.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def serve(workspace: Path, host=None, port=None):
    secret = os.environ.get("IMPACT_WEBHOOK_TOKEN", "")
    if not secret:
        raise RuntimeError("Set IMPACT_WEBHOOK_TOKEN before starting the Jira webhook server")
    ready_status = os.environ.get("IMPACT_JIRA_READY_STATUS", "Ready for Impact Analysis")
    criteria_field = os.environ.get("IMPACT_JIRA_CRITERIA_FIELD", "customfield_10000")
    workflow = AssessmentWorkflow(workspace)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/webhook/jira":
                return self.respond(404, {"error": "not_found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    return self.respond(400, {"error": "invalid_body_size"})
                raw_body = self.rfile.read(length)
                supplied_signature = self.headers.get("X-Hub-Signature", "")
                expected_signature = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
                custom_token = self.headers.get("X-Impact-Webhook-Token", "")
                signature_ok = hmac.compare_digest(supplied_signature, expected_signature)
                token_ok = hmac.compare_digest(custom_token.encode(), secret.encode())
                if not (signature_ok or token_ok):
                    return self.respond(401, {"error": "unauthorized"})
                payload = json.loads(raw_body)
                result = process_transition(payload, workflow, JiraClient(), ready_status, criteria_field)
                status = 200 if result.get("status") != "ignored" else 202
                self.respond(status, result)
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                self.respond(502, {"error": "assessment_or_delivery_failed", "type": type(exc).__name__})

    listen_host = host or os.environ.get("IMPACT_WEBHOOK_HOST", "127.0.0.1")
    listen_port = int(port or os.environ.get("IMPACT_WEBHOOK_PORT", "8082"))
    server = ThreadingHTTPServer((listen_host, listen_port), Handler)
    print(json.dumps({"service": "jira-impact-webhook", "host": listen_host, "port": listen_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
