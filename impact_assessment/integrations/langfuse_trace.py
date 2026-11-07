"""Optional Langfuse export for the evidence-backed assessment trace."""
from __future__ import annotations

import itertools
import os
import re
import sys
from typing import Any


REQUIRED_SETTINGS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
AGENT_NAMES = {"impact-investigation", "technical-debt", "risk-report"}


def _safe_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Keep useful trace metadata while avoiding full ticket or document text."""
    safe = {}
    for key, value in parameters.items():
        if key in {"query", "query_terms"}:
            terms = value if isinstance(value, (list, tuple)) else [value]
            safe["query_term_count"] = len(terms)
            if os.environ.get("LANGFUSE_INCLUDE_QUERY_TERMS", "").lower() in {"1", "true", "yes"}:
                safe["query_terms"] = [_mask(str(term))[:120] for term in terms[:20]]
            continue
        if key.lower() in {"text", "ticket_text", "description", "summary", "excerpt", "body", "payload"}:
            continue
        safe[key] = _safe_value(value)
    return safe


def _mask(value: str) -> str:
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", value)
    value = re.sub(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)", "[phone]", value)
    value = re.sub(r"\b(?:sk|pk)-lf-[A-Za-z0-9_-]+\b", "[credential]", value)
    return value


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _mask(value[:500])
    if isinstance(value, dict):
        return _safe_parameters(value)
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:50]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:200]


def export_assessment(assessment) -> dict[str, str | None]:
    """Send one nested trace when configured; tracing never blocks an assessment."""
    if not all(os.environ.get(name) for name in REQUIRED_SETTINGS):
        return {"status": "not_configured", "trace_id": None, "trace_url": None}

    try:
        from langfuse import get_client

        client = get_client()
        context = assessment.context
        with client.start_as_current_observation(
            as_type="span",
            name="ecommerce-impact-assessment",
            input={"ticket_id": context.ticket_id,
                   "ticket_version": context.ticket_version,
                   "snapshot_id": context.snapshot_id},
            metadata={"workflow": "evidence-impact-assessment",
                      "local_run_id": context.run_id,
                      "repository_count": str(len(context.repositories))},
        ) as root:
            for agent, events in itertools.groupby(assessment.trace, key=lambda event: event.agent):
                event_list = list(events)
                if agent in AGENT_NAMES:
                    with client.start_as_current_observation(
                        as_type="agent", name=agent,
                        input={"event_count": len(event_list)},
                        metadata={"local_run_id": context.run_id},
                    ) as agent_span:
                        _export_events(client, event_list)
                        agent_span.update(output={"events": len(event_list),
                                                  "outcomes": [event.outcome for event in event_list]})
                else:
                    _export_events(client, event_list)

            trace_id = root.trace_id
            root.update(output={
                "status": assessment.status,
                "impact_count": len(assessment.impacts),
                "risk_count": len(assessment.risks),
                "question_count": len(assessment.questions),
                "evidence_count": len(assessment.evidence),
                "repositories": sorted({item.repository for item in assessment.impacts}),
            })
        client.flush()
        trace_url = client.get_trace_url(trace_id=trace_id) if trace_id else None
        return {"status": "sent", "trace_id": trace_id, "trace_url": trace_url}
    except Exception as exc:  # Optional telemetry must not fail the assessment.
        print(f"Langfuse trace export failed ({type(exc).__name__})", file=sys.stderr)
        return {"status": "error", "trace_id": None, "trace_url": None}


def _export_events(client, events) -> None:
    for event in events:
        if event.event_type == "tool":
            observation_type = "retriever" if event.name == "search-evidence" else "tool"
        else:
            observation_type = "span"
        with client.start_as_current_observation(
            as_type=observation_type,
            name=event.name,
            input=_safe_parameters(event.parameters),
            metadata={"agent": event.agent, "event_type": event.event_type,
                      "local_run_id": event.run_id},
        ) as observation:
            observation.update(
                output={"outcome": event.outcome,
                        "evidence_ids": event.evidence_ids,
                        "duration_ms": event.duration_ms,
                        "error": type(event.error).__name__ if event.error else None},
                level="ERROR" if event.outcome in {"error", "failed", "timeout"} else "DEFAULT",
            )
