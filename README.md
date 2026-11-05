# E-commerce impact assessment

This workspace contains six sample commerce services and a local, evidence-backed impact assessment prototype. The assessment agents inspect tickets and repository evidence; they do not edit application code.

## Run a local assessment

From this workspace root:

```bash
python3.11 -m impact_assessment index
python3.11 -m impact_assessment assess \
  --ticket-id DEMO-DELIVERY-1 \
  --ticket-version 1 \
  --summary "Pass delivery instructions from checkout to the carrier and customer confirmation" \
  --description "Customers can add delivery instructions at checkout. Forward them to the carrier and include them in the shipment confirmation."
```

To run the same workflow through LangGraph, install the optional runtime and add `--orchestrator langgraph`:

```bash
python3.11 -m pip install -r requirements-agent-runtime.txt
python3.11 -m impact_assessment assess --orchestrator langgraph \
  --ticket-id DEMO-DELIVERY-1 --summary "Pass delivery instructions to the carrier" \
  --description "Forward optional delivery instructions from checkout to the carrier and shipment confirmation."
```

The CLI writes an immutable local snapshot and a run directory under `.impact_assessment/`. Each run contains `assessment.json`, `report.md`, and `trace.ndjson`. The default three-hour debt ceiling is per item and includes testing. Current sample debt estimates are marked illustrative, so the agent will ask for confirmation instead of treating them as approved effort.

The local prototype uses deterministic lexical retrieval and extracts configured HTTP and ActiveMQ topic relationships from the service configs. Optional LangGraph orchestration and a read-only MCP server are implemented; Jira intake and report delivery are also wired but not connected to an account. The default path does not use Pinecone, Neo4j, a language model, or Langfuse. The target design and integration order are in [the architecture and implementation plan](plan/agent-architecture-and-mvp.md).

## Jira transition integration

The Jira adapter is implemented, but requires an externally reachable HTTPS endpoint and Jira credentials. Configure these environment variables outside the repository:

```bash
export IMPACT_WEBHOOK_TOKEN='a-long-random-secret'
export IMPACT_JIRA_BASE_URL='https://your-site.atlassian.net'
export IMPACT_JIRA_EMAIL='jira-bot@example.com'
export IMPACT_JIRA_API_TOKEN='your-api-token'
export IMPACT_JIRA_READY_STATUS='Ready for Impact Analysis'
export IMPACT_JIRA_CRITERIA_FIELD='customfield_10000'
python3.11 -m impact_assessment webhook
```

Register a Jira issue-updated webhook for the target project and status transition, configured to sign the request with the same secret (Jira `X-Hub-Signature`), or configure the custom header `X-Impact-Webhook-Token`. The local listener binds to `127.0.0.1:8082`; set `IMPACT_WEBHOOK_HOST=0.0.0.0` behind an authenticated HTTPS ingress when deploying. It re-fetches the issue, deduplicates by issue version and evidence snapshot, persists the report, and skips duplicate Jira comments. If Jira delivery fails after persistence, retry with `python3.11 -m impact_assessment deliver <run-id>`. The Jira issue REST user needs permission to read the issue and create/read comments.

## MCP evidence tools

After indexing, start `python3.11 -m impact_assessment mcp` from the workspace root. This read-only stdio server pins itself to the current snapshot and exposes documentation/debt search, exact identifier search, bounded graph traversal, evidence fetch, and contract lookup. Add that command to the agent host's MCP server configuration. It cannot write snapshots or commerce repositories.

## Browser demo

Start the local UI from the workspace root:

```bash
python3.11 -m impact_assessment ui
```

Open [http://127.0.0.1:8088](http://127.0.0.1:8088). The Impact assessment tab runs the evidence-backed workflow against the current local snapshot and shows findings, risks, debt overlap, evidence, and trace. The Commerce journey tab sends a checkout through the local services and displays asynchronous shipment and notification updates. It uses synthetic local payment and carrier providers; no real payment or shipment is created. Service status is liveness only and does not confirm that broker workers are subscribed.

## Evidence graph, hosted stores, and evaluation

Graphify is installed in the active `.venv`. Rebuild its local code graph and reconcile it against the implementation-reviewed contracts:

```bash
.venv/bin/python -m impact_assessment extract-graph
```

The code-only Graphify graph and reconciliation report are written under `.impact_assessment/graphify/` and are ignored by Git. The latest extraction parsed 78 source files into 596 nodes and 1,241 AST edges. It found no cross-service source-code edges because the six applications are separate packages. The pipeline retains HTTP, ActiveMQ, and field-mapping relationships from each service's `contracts.json` as explicit, evidence-cited graph edges.

To publish a snapshot, configure a Pinecone index with an integrated text embedding model mapped to the `text` field, plus a Neo4j database. Set these deployment secrets in the shell or hosting platform:

```text
PINECONE_API_KEY
PINECONE_INDEX_HOST
NEO4J_URI
NEO4J_USERNAME
NEO4J_PASSWORD
NEO4J_DATABASE   # optional; defaults to neo4j
```

Then install optional runtime packages and publish:

```bash
.venv/bin/python -m pip install -r requirements-agent-runtime.txt
.venv/bin/python -m impact_assessment publish --dry-run
.venv/bin/python -m impact_assessment publish
```

Pinecone records are namespaced by evidence snapshot and carry repository, commit, source path, line range, document type, and snapshot ID. Neo4j stores Graphify source nodes and edges alongside contract-derived service, event, and field-mapping relationships. The CLI reports a completed publish marker only after both services accept the snapshot. Hosted assessment retrieval is opt-in with `IMPACT_EVIDENCE_BACKEND=hosted`; it refuses to use a snapshot without that marker. The local default remains available without hosted credentials. Pinecone's integrated embedding setup is described in its [index configuration docs](https://docs.pinecone.io/reference/api/2025-10/control-plane/configure_index); the Neo4j adapter uses the official [Python driver](https://neo4j.com/docs/python-manual/current/).

The fixed eight-ticket replay set and its provisional labels are in [evaluation/benchmark-v1.json](evaluation/benchmark-v1.json). The answer key sits outside `sample-repositories/`, so it is not included in evidence retrieval. Run it with:

```bash
IMPACT_EVIDENCE_BACKEND=local .venv/bin/python -m impact_assessment evaluate
```

Results are saved under `.impact_assessment/evaluations/`. Current replay results on the local corpus: 100% micro precision, 100% micro recall, zero invalid evidence/path references, zero payment-scope violations in the inventory case, zero ineligible debt recommendations, and zero tool errors. These scores are **not a release gate**: labels are provisional pending domain-owner review, and the matching checkout debt estimate is illustrative rather than team-approved. The replay also confirms the ambiguous expedited-shipping case returns focused timing, cost, and eligibility questions.

The coordinator allows up to two targeted evidence reinvestigation rounds, shares its tool-call budget across those rounds, recalculates debt decisions after revised findings, and records routing and evidence details in the trace. The demo UI exposes each trace event's parameters, outcomes, evidence IDs, and timings.

## Replit configuration and deployment boundary

The root [.replit](.replit) file configures the UI command for the workspace and a Replit deployment. The listener uses Replit's `PORT` and public interface when present, and requires `IMPACT_UI_TOKEN` before binding outside loopback. The UI accepts service URLs through `IMPACT_URL_COMMERCE_CHECKOUT`, `IMPACT_URL_COMMERCE_ORDERS`, `IMPACT_URL_COMMERCE_INVENTORY`, `IMPACT_URL_COMMERCE_PAYMENTS`, `IMPACT_URL_COMMERCE_SHIPPING`, `IMPACT_URL_COMMERCE_NOTIFICATIONS`, `IMPACT_URL_PAYMENT_PROVIDER_API`, and `IMPACT_URL_CARRIER_PROVIDER_API`; broker reachability uses `IMPACT_BROKER_HOST` and `IMPACT_BROKER_PORT`. Set `COMMERCE_API_TOKEN` for authenticated service APIs and `PAYMENT_PROVIDER_API_TOKEN` / `CARRIER_PROVIDER_API_TOKEN` if the provider mocks also require tokens. Enter the UI token in the access dialog; it is kept in browser session storage.

This config has not been deployed or validated in a Replit account. Replit must also provide reachable service APIs, ActiveMQ, payment/carrier mock APIs, and hosted evidence stores if hosted retrieval is enabled. The workspace UI adds bearer-token checks, same-origin validation, request-size and per-client rate limits, and browser security headers. Sample service APIs now enforce shared bearer-token authentication when configured and refuse non-loopback/non-local startup without `COMMERCE_API_TOKEN`; `/health` remains public for liveness. Configure the same token for service-to-service requests and the UI. This is a basic demo boundary, not a substitute for TLS, per-service identities, authorization scopes, or production reliability controls; do not expose these APIs directly to the public internet. See [Replit project configuration](https://docs.replit.com/references/project-setup/configuration) for deployment settings.
