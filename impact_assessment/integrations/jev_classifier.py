"""Typed Jira impact classification via the Jev decision API."""
from __future__ import annotations

import hashlib
import json
import os
import time
from urllib import error, request


IMPACT_SCOPE = {
    "single_service": "A bounded change in one named service or component.",
    "multi_service": "A specific, traceable flow crossing two or more services.",
    "cross_cutting": "A broad platform or reliability request without a narrow service path.",
    "unclear": "The ticket does not identify a scope that can be classified reliably.",
}
CHANGE_KIND = {
    "api_or_field_contract": "A REST API, request/response field, schema, or field mapping change.",
    "event_or_message_flow": "An event, message, topic, producer, consumer, or delivery-flow change.",
    "business_rule": "A commerce rule such as inventory, eligibility, pricing, or order behavior.",
    "external_provider_mapping": "A payment, carrier, or other external provider request/response mapping.",
    "notification_or_presentation": "Customer notification content, template, or presentation only.",
    "data_validation_or_testing": "Validation logic or test behavior, with no broader behavior change specified.",
    "reliability_or_persistence": "Retries, durability, idempotency, persistence, or recovery behavior.",
    "mixed_or_unclear": "Multiple kinds are central, or the ticket lacks enough detail to choose one.",
}
CLARITY_SCALE = [
    "Clear: behavior and scope are specific enough to investigate.",
    "Mostly clear: minor details remain, but the intended change is bounded.",
    "Materially underspecified: product or technical decisions could change the design.",
    "Blocked: the core scope or expected outcome is too broad or missing.",
]
RETRYABLE_STATUSES = {429, 499, 502, 503, 504}


def _answer_choice(answers, name):
    item = answers.get(name) or {}
    return {
        "label": item.get("choice"),
        "confidence": item.get("confidence"),
        "probabilities": item.get("probabilities", {}),
    }


def _ticket_state(ticket):
    criteria = ticket.get("acceptance_criteria") or []
    return {
        "summary": str(ticket.get("summary", ""))[:500],
        "description": str(ticket.get("description", ""))[:10000],
        "acceptance_criteria": [str(item)[:600] for item in criteria[:20]],
    }


def _retry_after(headers):
    value = headers.get("Retry-After") if headers else None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _classify_jira_requirement_jev(ticket: dict, trace=None):
    """Return a typed, advisory classification. No classification is fabricated offline."""
    api_key = os.environ.get("JEV_API_KEY")
    if not api_key or os.environ.get("JEV_CLASSIFICATION_ENABLED", "true").lower() in {"0", "false", "no", "off"}:
        status = "disabled" if os.environ.get("JEV_CLASSIFICATION_ENABLED", "true").lower() in {"0", "false", "no", "off"} else "not_configured"
        if trace:
            trace.add("jev-classifier", "classification", "jira-impact-classification",
                      {"provider": "jev", "status": status}, outcome="skipped")
        return status, None

    model = os.environ.get("JEV_MODEL", "jev-1.13")
    if model not in {"jev-1.13", "jev-latest"}:
        if trace:
            trace.add("jev-classifier", "classification", "jira-impact-classification",
                      {"provider": "jev", "model": model}, outcome="error", error="invalid_model")
        return "unavailable", None
    state = _ticket_state(ticket)
    payload = {
        "model": model,
        "state": state,
        "questions": {
            "impact_scope": {
                "type": "choice",
                "instructions": "Classify the likely breadth of this Jira change request from the ticket text alone.",
                "criteria": IMPACT_SCOPE,
            },
            "change_kind": {
                "type": "choice",
                "instructions": "Choose the primary type of change requested by this Jira ticket.",
                "criteria": CHANGE_KIND,
            },
            "clarity": {
                "type": "score",
                "instructions": "Score how clearly the ticket defines its scope and expected behavior.",
                "criteria": CLARITY_SCALE,
            },
            "requires_clarification": {
                "type": "noul",
                "instructions": "Would a responsible engineer need product or technical clarification before committing to an implementation plan?",
            },
        },
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    idempotency_key = hashlib.sha256(body).hexdigest()
    timeout = float(os.environ.get("JEV_TIMEOUT_SECONDS", "20"))
    started = time.monotonic()
    result = None
    error_code = None
    for attempt in range(4):
        req = request.Request(
            "https://jev-ai.org/api/v1/systemone/", data=body, method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                     "Idempotency-Key": idempotency_key},
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read())
            break
        except error.HTTPError as exc:
            status_code = exc.code
            error_code = None
            retry_wait = _retry_after(exc.headers)
            try:
                body_error = json.loads(exc.read())
                error_code = (body_error.get("error") or {}).get("code")
            except (ValueError, TypeError):
                pass
            exc.close()
            if status_code not in RETRYABLE_STATUSES or attempt >= 3:
                if trace:
                    trace.add("jev-classifier", "classification", "jira-impact-classification",
                              {"provider": "jev", "model": model, "http_status": status_code,
                               "error_code": error_code}, outcome="error",
                              error="jev_request_failed", duration_ms=round((time.monotonic() - started) * 1000, 2))
                return "unavailable", None
            time.sleep(retry_wait if retry_wait is not None else 0.5 * (2 ** attempt))
        except (error.URLError, TimeoutError, OSError):
            if attempt >= 3:
                if trace:
                    trace.add("jev-classifier", "classification", "jira-impact-classification",
                              {"provider": "jev", "model": model}, outcome="error",
                              error="network_error", duration_ms=round((time.monotonic() - started) * 1000, 2))
                return "unavailable", None
            time.sleep(0.5 * (2 ** attempt))
        except ValueError:
            if trace:
                trace.add("jev-classifier", "classification", "jira-impact-classification",
                          {"provider": "jev", "model": model}, outcome="error", error="invalid_response")
            return "unavailable", None

    if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
        if trace:
            trace.add("jev-classifier", "classification", "jira-impact-classification",
                      {"provider": "jev", "model": model}, outcome="error", error="invalid_response")
        return "unavailable", None

    answers = result["answers"]
    scope = _answer_choice(answers, "impact_scope")
    kind = _answer_choice(answers, "change_kind")
    if scope["label"] not in IMPACT_SCOPE or kind["label"] not in CHANGE_KIND:
        if trace:
            trace.add("jev-classifier", "classification", "jira-impact-classification",
                      {"provider": "jev", "model": model}, outcome="error", error="invalid_label")
        return "unavailable", None

    try:
        scope_confidence = float(scope["confidence"] or 0.0)
        kind_confidence = float(kind["confidence"] or 0.0)
        clarity_answer = answers.get("clarity") or {}
        probabilities = clarity_answer.get("probabilities", {})
        best_tier = max(probabilities, key=probabilities.get) if probabilities else None
        legend = clarity_answer.get("legend", {})
        clarification_probability = (answers.get("requires_clarification") or {}).get("noul")
        clarity_value = float(clarity_answer.get("score", 0.0))
        if clarification_probability is not None:
            clarification_probability = float(clarification_probability)
    except (TypeError, ValueError, AttributeError):
        if trace:
            trace.add("jev-classifier", "classification", "jira-impact-classification",
                      {"provider": "jev", "model": model}, outcome="error", error="invalid_response")
        return "unavailable", None
    classification = {
        "provider": "jev",
        "model": result.get("model", model),
        "model_version": result.get("model_version"),
        "impact_scope": scope,
        "change_kind": kind,
        "clarity": {"score": clarity_value, "label": legend.get(best_tier),
                    "probabilities": probabilities, "confidence": clarity_answer.get("confidence")},
        "requires_clarification_probability": clarification_probability,
        "review_recommended": (
            scope_confidence < 0.75 or kind_confidence < 0.75 or clarity_value >= 2.0
            or (clarification_probability is not None and float(clarification_probability) >= 0.65)
        ),
        "request_id": result.get("id"),
        "input_tokens": (result.get("usage") or {}).get("input_tokens"),
    }
    status = "needs_review" if classification["review_recommended"] else "ready"
    if trace:
        trace.add("jev-classifier", "classification", "jira-impact-classification",
                  {"provider": "jev", "model": classification["model"],
                   "model_version": classification["model_version"], "impact_scope": scope["label"],
                   "scope_confidence": scope_confidence, "change_kind": kind["label"],
                   "kind_confidence": kind_confidence, "review_recommended": classification["review_recommended"],
                   "input_tokens": classification["input_tokens"]},
                  outcome=status, duration_ms=round((time.monotonic() - started) * 1000, 2))
    return status, classification


def classify_jira_requirement(ticket: dict, trace=None):
    """Dispatch to Jev or OpenAI; auto mode uses OpenAI when Jev is unavailable/disabled."""
    enabled = os.environ.get("IMPACT_CLASSIFICATION_ENABLED", "true").lower()
    if enabled in {"0", "false", "no", "off"}:
        if trace:
            trace.add("classifier-router", "routing", "jira-impact-classification",
                      {"provider": "none"}, outcome="skipped")
        return "disabled", None

    provider = os.environ.get("IMPACT_CLASSIFIER_PROVIDER", "auto").strip().lower()
    if provider not in {"auto", "jev", "openai", "disabled"}:
        if trace:
            trace.add("classifier-router", "routing", "jira-impact-classification",
                      {"provider": provider}, outcome="error", error="invalid_classifier_provider")
        return "unavailable", None
    if provider == "disabled":
        return "disabled", None

    jev_enabled = os.environ.get("JEV_CLASSIFICATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
    has_jev = bool(os.environ.get("JEV_API_KEY")) and jev_enabled
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))

    if provider == "jev":
        if not jev_enabled:
            return "disabled", None
        if not os.environ.get("JEV_API_KEY"):
            return "not_configured", None
        return _classify_jira_requirement_jev(ticket, trace)

    if provider == "openai":
        from .openai_classifier import classify_jira_requirement_openai
        return classify_jira_requirement_openai(ticket, trace)

    if has_jev:
        status, classification = _classify_jira_requirement_jev(ticket, trace)
        if classification is not None:
            return status, classification
        if trace and has_openai:
            trace.add("classifier-router", "routing", "fallback-to-openai-classifier",
                      {"from": "jev", "to": "openai"}, outcome="fallback")
    if has_openai:
        from .openai_classifier import classify_jira_requirement_openai
        return classify_jira_requirement_openai(ticket, trace)

    status = "disabled" if not jev_enabled else "not_configured"
    if trace:
        trace.add("classifier-router", "routing", "jira-impact-classification",
                  {"provider": provider, "jev_available": bool(os.environ.get("JEV_API_KEY")),
                   "openai_available": has_openai}, outcome="skipped")
    return status, None
