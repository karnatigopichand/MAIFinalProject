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

The local prototype uses deterministic lexical retrieval and extracts configured HTTP and ActiveMQ topic relationships from the service configs. Optional LangGraph orchestration, read-only MCP retrieval, and Langfuse tracing are implemented; Jira intake and report delivery are wired but not connected to an account. Pinecone, Neo4j, and Langfuse are optional: the local workflow continues without hosted credentials. The target design and integration order are in [the architecture and implementation plan](plan/agent-architecture-and-mvp.md).

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

### Pull an issue from the browser UI

The assessment tab can also fetch one Jira issue by key without waiting for a status transition. Set `IMPACT_JIRA_BASE_URL`, `IMPACT_JIRA_EMAIL`, and `IMPACT_JIRA_API_TOKEN` in the environment that starts the UI. For example, from the project root, load your private `.env` into the shell and start the UI:

```bash
set -a
source .env
set +a
python3.11 -m impact_assessment ui
```

In the UI, enter an issue key such as `SHOP-123`, select **Load issue from Jira**, review the summary, description, and acceptance criteria, then select **Run impact assessment**. The app reads that issue directly from Jira; it does not enumerate a board. The Jira account needs permission to browse the project and read the issue. Acceptance criteria are read from `IMPACT_JIRA_CRITERIA_FIELD`, defaulting to `customfield_10000`. Missing Jira settings and Jira API errors are shown in the UI. Keep the API token server-side and out of chat, browser code, and source control.

## MCP evidence tools

Install `requirements-agent-runtime.txt`, index the corpus, then start `python3.11 -m impact_assessment mcp` from the workspace root. This read-only stdio server pins itself to the current snapshot and exposes `search_evidence` (RAG retrieval with document-type filters), `search_docs`, `search_technical_debt`, `list_technical_debt`, `search_identifiers`, `traverse_dependencies`, `fetch_evidence`, `get_contract`, and `classify_jira_impact`. Results retain snapshot IDs and evidence provenance; dependency traversal has hop and result bounds. `classify_jira_impact` uses the configured classifier provider and sends ticket text to that provider. Add that command to the agent host's MCP server configuration. The MCP interface cannot write snapshots or commerce repositories.

The assessment workflow currently calls the shared evidence store directly; MCP is provided as the interoperable retrieval interface for MCP-capable agent hosts and inspection clients. The retrieval ranking is local lexical/BM25-style matching by default, with Pinecone as an optional hosted vector backend. Neo4j stores dependency edges for hosted graph traversal. Search results are candidates: findings still require source evidence and graph paths are limited to edges present in the pinned snapshot.

Each assessment gets an advisory impact classification for scope, primary change kind, clarity, and clarification need. Set `IMPACT_CLASSIFIER_PROVIDER=auto` (default), `jev`, or `openai`; auto prefers Jev when enabled and available, then uses OpenAI if Jev is absent or unavailable. OpenAI uses `OPENAI_API_KEY` and `IMPACT_CLASSIFIER_MODEL` (default `CHAT_MODEL` or `gpt-4o-mini`) with a structured response schema. `JEV_CLASSIFICATION_ENABLED=false` skips Jev but still allows OpenAI fallback; `IMPACT_CLASSIFICATION_ENABLED=false` disables classification entirely. The selected provider receives the ticket summary, description, and acceptance criteria, and may incur API usage charges. Low confidence or material ambiguity sets a review flag; classification does not replace evidence tracing or create impact findings.

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

The project now uses a dedicated Pinecone index with integrated `llama-text-embed-v2` embeddings. The repository `.env` contains `PINECONE_INDEX` and `PINECONE_INDEX_HOST`; keep `PINECONE_API_KEY` private. To publish the current validated evidence snapshot to Pinecone only (dependency traversal stays on the local evidence graph), run:

```bash
set -a; source .env; set +a
.venv/bin/python -m impact_assessment publish-pinecone
```

This writes snapshot-scoped records and a local provenance marker under `.impact_assessment/pinecone/`. The command verifies Pinecone's record count and runs a semantic read-after-write query before it reports success. To run assessments against those vectors, start the process with `IMPACT_EVIDENCE_BACKEND=pinecone`:

```bash
set -a; source .env; set +a
IMPACT_EVIDENCE_BACKEND=pinecone .venv/bin/python -m impact_assessment ui
```

For the combined Pinecone plus Neo4j hosted pipeline, configure a Neo4j database and set these deployment secrets in the shell or hosting platform:

```text
PINECONE_API_KEY
PINECONE_INDEX_HOST or PINECONE_INDEX
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

Pinecone records are namespaced by evidence snapshot and carry repository, commit, source path, line range, document type, and snapshot ID. Neo4j stores Graphify source nodes and edges alongside contract-derived service, event, and field-mapping relationships. The combined `publish` command reports a completed marker only after both services accept the snapshot. Hosted assessment retrieval is opt-in with `IMPACT_EVIDENCE_BACKEND=hosted`; Pinecone-only retrieval uses `IMPACT_EVIDENCE_BACKEND=pinecone`. Both modes refuse to use an unpublished snapshot. Pinecone's integrated embedding setup is described in its [index configuration docs](https://docs.pinecone.io/reference/api/2025-10/control-plane/configure_index); the Neo4j adapter uses the official [Python driver](https://neo4j.com/docs/python-manual/current/).

### Use the Neo4j graph

Neo4j contains versioned `ImpactNode` nodes and relationship edges. Contract relationships include `CALLS`, `PUBLISHES`, `CONSUMES`, `DECLARES_FIELD`, and `MAPS_TO`; Graphify code relationships use `GRAPHIFY_EDGE`. Every stored item has a `snapshot_id`, so graph queries should filter to the ID printed by `publish`.

1. Configure Neo4j connection variables and the Pinecone variables above in your shell or hosting secrets. Install the optional packages if needed.
2. Run `extract-graph`, then `publish`. Publishing validates and writes both Pinecone and Neo4j; copy the resulting `snapshot_id`.
3. In Neo4j Browser, set that ID and inspect the checkout to notification path:

```cypher
:param snapshot_id => 'PASTE_SNAPSHOT_ID';

MATCH p=(s:ImpactNode {snapshot_id: $snapshot_id, node_id: 'commerce-checkout'})-[*1..3]->
  (t:ImpactNode {snapshot_id: $snapshot_id, node_id: 'commerce-notifications'})
WHERE all(r IN relationships(p) WHERE type(r) IN ['CALLS', 'PUBLISHES', 'CONSUMES'])
RETURN [n IN nodes(p) | n.node_id] AS services_and_events,
       [r IN relationships(p) | {type: type(r), detail: r.detail, evidence: r.evidence_ids}] AS contracts;
```

To use this graph during assessments, set `IMPACT_EVIDENCE_BACKEND=hosted` in the process environment and run the usual `assess` command. Hosted mode combines Neo4j dependency traversal with Pinecone semantic search; both stores must contain the current snapshot. Local mode uses the SQLite-backed evidence snapshot and does not contact Neo4j.

### Langfuse traces

Langfuse export is optional. Install the SDK with `python -m pip install 'langfuse>=5,<6'` (or reinstall `requirements-agent-runtime.txt`), then set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` in the environment that starts the app. Create project keys in Langfuse Settings → API Keys; use the base URL for your Langfuse region or self-hosted instance. Never put the secret key in browser code.

Each assessment sends one named trace with nested agent, retriever, tool, and coordinator observations. The assessment response includes an “Open Langfuse trace” link when Langfuse returns one. Ticket descriptions and evidence excerpts are not exported. Search terms are omitted by default; set `LANGFUSE_INCLUDE_QUERY_TERMS=true` only when you have reviewed the data exposure for your tickets. Without the three settings, assessments continue normally and the local `trace.ndjson` remains available in each run directory. See the [Langfuse Python SDK guide](https://langfuse.com/docs/observability/sdk/overview) and [trace best practices](https://langfuse.com/docs/observability/best-practices).

### Code recommendations from web research

When `OPENAI_API_KEY` is configured, each assessment with verified impact findings can request up to three small code or test recommendations through the OpenAI Responses API web-search tool. The search is restricted to official project documentation and standards sources, and each displayed recommendation must include a URL returned by the search. Recommendations appear inside the collapsible assessment response and in the downloadable report; the assessment trace records the search model, source count, and result count. The recommendation request sends only the ticket summary, evidence-backed impact claims, and relevant repository paths; it does not send ticket descriptions or source excerpts. Set `CODE_RECOMMENDATIONS_ENABLED=false` to disable these requests, or set `CODE_RECOMMENDATION_MODEL` to override the existing `CHAT_MODEL`. Web search and model usage are billed by the OpenAI API; see the [web-search documentation](https://developers.openai.com/api/docs/guides/tools-web-search) and [API pricing](https://developers.openai.com/api/docs/pricing). Recommendations are advisory and do not edit application code.

The fixed eight-ticket replay set and its provisional labels are in [evaluation/benchmark-v1.json](evaluation/benchmark-v1.json). The answer key sits outside `sample-repositories/`, so it is not included in evidence retrieval. Run it with:

```bash
IMPACT_EVIDENCE_BACKEND=local .venv/bin/python -m impact_assessment evaluate
```

The default replay forces the local backend and disables Jev/OpenAI classification, web recommendations, and Langfuse export so it stays deterministic and offline. It reports repository precision/recall, retrieved-evidence repository recall, citation/path validity, ambiguity-question checks, debt eligibility, and tool errors. Labels remain provisional.

Each case also has provisional Jira impact labels for scope and change kind. To run Jev classification scoring, set `JEV_API_KEY` in the server environment and run:

```bash
.venv/bin/python -m impact_assessment evaluate --jev-classification
```

For an advisory LLM-as-a-judge review, run:

```bash
.venv/bin/python -m impact_assessment evaluate --llm-judge
```

The judge uses `OPENAI_API_KEY` and `EVAL_JUDGE_MODEL` (default `gpt-4.1-mini`). It sends each ticket, report fields, and retrieved evidence excerpts to OpenAI; this can incur charges and should only be run with data approved for that service. Jev classification also sends ticket text to Jev and may incur usage charges. Both options can be combined. Results are saved under `.impact_assessment/evaluations/`; the LLM rubric in [evaluation/llm-judge-rubric-v1.md](evaluation/llm-judge-rubric-v1.md) is a candidate and remains advisory until calibrated against domain-owner labels. Do not use it as a release gate.

Results are saved under `.impact_assessment/evaluations/`. Rerun the command after changing the corpus, retrieval, agent logic, or benchmark labels; do not treat a previous local result as current. Scores are **not a release gate**: labels are provisional pending domain-owner review, and the matching checkout debt estimate is illustrative rather than team-approved. The ambiguous expedited-shipping case is intended to exercise focused timing, cost, and eligibility questions.

The coordinator allows up to two targeted evidence reinvestigation rounds, shares its tool-call budget across those rounds, recalculates debt decisions after revised findings, and records routing and evidence details in the trace. The demo UI keeps the full assessment response collapsible, exposes the local trace event details, and links to Langfuse when remote tracing is configured.

## Replit configuration and deployment boundary

The root [.replit](.replit) file configures the UI command for the workspace and a Replit deployment. The listener uses Replit's `PORT` and public interface when present, and requires `IMPACT_UI_TOKEN` before binding outside loopback. The UI accepts service URLs through `IMPACT_URL_COMMERCE_CHECKOUT`, `IMPACT_URL_COMMERCE_ORDERS`, `IMPACT_URL_COMMERCE_INVENTORY`, `IMPACT_URL_COMMERCE_PAYMENTS`, `IMPACT_URL_COMMERCE_SHIPPING`, `IMPACT_URL_COMMERCE_NOTIFICATIONS`, `IMPACT_URL_PAYMENT_PROVIDER_API`, and `IMPACT_URL_CARRIER_PROVIDER_API`; broker reachability uses `IMPACT_BROKER_HOST` and `IMPACT_BROKER_PORT`. Set `COMMERCE_API_TOKEN` for authenticated service APIs and `PAYMENT_PROVIDER_API_TOKEN` / `CARRIER_PROVIDER_API_TOKEN` if the provider mocks also require tokens. Enter the UI token in the access dialog; it is kept in browser session storage.

This config has not been deployed or validated in a Replit account. Replit must also provide reachable service APIs, ActiveMQ, payment/carrier mock APIs, and hosted evidence stores if hosted retrieval is enabled. The workspace UI adds bearer-token checks, same-origin validation, request-size and per-client rate limits, and browser security headers. Sample service APIs now enforce shared bearer-token authentication when configured and refuse non-loopback/non-local startup without `COMMERCE_API_TOKEN`; `/health` remains public for liveness. Configure the same token for service-to-service requests and the UI. This is a basic demo boundary, not a substitute for TLS, per-service identities, authorization scopes, or production reliability controls; do not expose these APIs directly to the public internet. See [Replit project configuration](https://docs.replit.com/references/project-setup/configuration) for deployment settings.
