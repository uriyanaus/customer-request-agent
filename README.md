# Autonomous Customer Request Agent

An agent that takes a **free-text customer request**, reasons over customer/order
data using tools, and returns a structured decision — `APPROVE`, `REJECT`, or
`ESCALATE` — with a full reasoning trace.

It's a **hybrid** design: an LLM (or a deterministic fallback) *understands* the
request, but a deterministic **rule engine** makes the actual money decision. The
LLM never decides a refund — which keeps every decision auditable and testable.

---

## Quickstart

No API key required — it runs out of the box in deterministic **mock mode**:

```bash
make install        # pip install -r requirements.txt  (just pydantic to run)
make samples        # run all bundled sample requests through the agent
```

Single request:

```bash
make run REQUEST="Refund for ORD1001, this is CUST001. It was $30."
# or, with no make:
python -m agent.cli "Refund for ORD1001, this is CUST001. It was $30."
```

Use the **real LLM** for parsing (Anthropic Claude) by setting a key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # AGENT_LLM=auto picks Claude when a key is present
python -m agent.cli --samples
```

---

## Architecture

The core is a small, cloud-agnostic pipeline. Adapters wrap it for the CLI (local)
and AWS Lambda (deployed) — the agent logic is identical in both.

```
free text
   │
   ▼
[ classify ]   LLM (Claude, structured output) OR mock regex extractor
   │           → ParsedRequest { request_type, customer_id, order_id, amount }
   ▼
[ tools    ]   lookup_customer() · get_order_history() · get_order()
   │
   ▼
[ rules    ]   deterministic engine, fixed precedence → APPROVE / REJECT / ESCALATE
   │
   ▼
AgentDecision (Pydantic)  { action, matched_rule, reasoning_trace, ... }  + JSON audit log
```

```
agent/
  models.py        Pydantic contracts (Action, RequestType, ParsedRequest, AgentDecision)
  config.py        thresholds + injected "today" (2026-06-16) + LLM selection
  classifier.py    AnthropicClassifier (structured output) | MockClassifier (regex)
  tools.py         the 2 tools over bundled JSON reference data
  rules.py         deterministic decision engine (the money decision)
  pipeline.py      orchestration: classify → tools → rules → AgentDecision
  cli.py           local entry point  (the "single command")
  lambda_handler.py AWS adapter (API Gateway → Lambda → JSON)
  data/            customers.json · orders.json · sample_requests.json
infra/             Terraform: sync API Gateway (HTTP) → Lambda
```

### Why hybrid (LLM + rule engine)?
The task is a **money decision**, so the verdict must be deterministic, auditable,
and unit-testable. I use the LLM only for the fuzzy part — turning messy free text
into structured fields — and hand the verdict to a pure rule function. An LLM that
"mostly" approves refunds correctly is a liability; a rule engine that always
applies the documented policy is not.

### The two tools
`lookup_customer(customer_id)` and `get_order_history(customer_id)` (plus a small
`get_order(order_id)` helper). They read bundled JSON today; swapping them for a
real datastore wouldn't touch the rest of the pipeline.

---

## Decision logic

Rules are evaluated in a **fixed precedence order** (first match wins). This makes
conflicts explicit — e.g. "no customer found" (REJECT) is checked before the dollar
thresholds, because you can't price a refund for a customer that doesn't exist.

| # | Condition | Decision | Rule id |
|---|---|---|---|
| 1 | Not a refund (account question / complaint / unknown) | `ESCALATE` | `non_refund_request` |
| 2 | Missing key info (customer_id / order_id / amount) | `ESCALATE` | `incomplete_request` |
| 3 | Customer id given but not found | `REJECT` | `no_matching_customer` |
| 4 | Order id given but not found | `REJECT` | `no_matching_order` |
| 5 | Order doesn't belong to that customer | `REJECT` | `order_customer_mismatch` |
| 6 | Customer not `active` (e.g. suspended) | `ESCALATE` | `customer_not_active` |
| 7 | Order not refundable (cancelled / refunded) | `ESCALATE` | `order_not_refundable` |
| 8 | Refund exceeds the order total | `ESCALATE` | `refund_exceeds_order_total` |
| 9 | Refund **over $500** | `ESCALATE` | `amount_over_500` |
| 10 | Order **older than 90 days** | `ESCALATE` | `order_older_than_90d` |
| 11 | Refund **under $50** AND order **within 30 days** | `APPROVE` | `under_50_within_30d` |
| 12 | Anything left (the gray band) | `ESCALATE` | `gray_area_review` |

Rules 1–4 and 9–11 are the assignment's spec. Rules 5–8 and 12 are **documented
extensions** (the task invites extending the rules) for cases the spec leaves open.

### Boundary semantics (documented choices)
The spec uses inclusive/exclusive words loosely, so I pinned them:

- **under $50** → `amount < 50` (strict). $50.00 is *not* auto-approved.
- **over $500** → `amount > 500` (strict). $500.00 is *not* auto-escalated by amount.
- **within 30 days** → `age_days <= 30`.
- **older than 90 days** → `age_days > 90`.
- **today** is injected as config (`2026-06-16`), never `datetime.now()`, so date
  math is deterministic and testable.

### The gray area
The spec calls out cases like "a $75 refund within 30 days" that match **no** rule.
My policy: anything that isn't explicitly auto-approvable and doesn't trip a hard
escalate threshold → **ESCALATE to human review** (`gray_area_review`). This is the
safe default for money. A natural extension (not built, to stay in scope) is
**tier-based limits** — e.g. let `premium`/`vip` customers auto-approve up to a
higher amount — using the `tier` field already present on each customer.

---

## Edge cases handled
- **Missing / ambiguous input** → `incomplete_request` (ESCALATE).
- **Unknown customer or order** → `REJECT`.
- **Order/customer mismatch** → `REJECT`.
- **Suspended customer / cancelled order / refund > order total** → `ESCALATE`.
- **Non-refund intents** (account question, complaint) → `ESCALATE` (route to human).
- **LLM failure** → classifier falls back to the deterministic regex extractor, so
  the pipeline always returns a decision.

---

## Structured output
Every run returns an `AgentDecision` (Pydantic → JSON). It deliberately carries
**no PII** — only the ids needed to audit the decision:

```json
{
  "action": "APPROVE",
  "matched_rule": "under_50_within_30d",
  "reasoning": "APPROVE via rule 'under_50_within_30d'.",
  "reasoning_trace": ["Parsed request: ...", "Resolved customer ...", "Order age is 15 days ...", "..."],
  "request": { "request_type": "REFUND", "customer_id": "CUST001", "order_id": "ORD1001", "amount": 30.0, "...": "..." },
  "customer_id": "CUST001",
  "order_id": "ORD1001",
  "llm_mode": "mock"
}
```

See [`examples/sample_outputs.md`](examples/sample_outputs.md) for representative
inputs and their full outputs (reproduce with `make samples`).

## Observability
Each decision also emits one **structured JSON audit event** to stderr (→ CloudWatch
under Lambda) with email PII redacted. Since the service is stateless, these log
events *are* the audit trail — persistence is a downstream concern, not coupled into
the request path.

## LLM usage / mocking
The classifier is one interface with two implementations. `AGENT_LLM=auto` (default)
uses **Claude (`claude-haiku-4-5`)** when `ANTHROPIC_API_KEY` is set, else the **mock**
regex extractor. The LLM only extracts fields (the cheap/fast model is enough — it
doesn't make the decision). Mock mode keeps the agent fully runnable, offline, and
reproducible, which is also what makes the examples deterministic.

---

## AWS deployment (Terraform)

A thin **synchronous** path: `API Gateway (HTTP) → Lambda → JSON decision`. The core
agent is unchanged; `lambda_handler.py` is just an adapter.

```bash
make deploy          # builds lambda.zip, then terraform init && apply
# → outputs api_endpoint; then:
curl -s -X POST "$API/decisions" -H 'content-type: application/json' \
     -d '{"request":"Refund for ORD1001, this is CUST001. $30"}'
make destroy         # tear down
```

Defaults to `AGENT_LLM=mock` so a deploy works with no key; set
`-var anthropic_api_key=... -var agent_llm=anthropic` to use Claude in the cloud.

---

## Key tradeoffs
- **Hybrid over a fully-autonomous tool-calling agent** — deterministic verdict,
  auditable, testable; the LLM is confined to NLU.
- **Sync over async** — simplest contract and easiest to demo for an interactive
  request. The right move once latency/throughput/retries matter is to make the
  Lambda an **SQS consumer** — an adapter swap, not a rewrite (see below).
- **Stateless over a database** — no infra to manage; decisions are emitted as
  structured audit events. Trade-off: no queryable history yet.
- **Bundled JSON over a datastore** — fine for an MVP; the tools are the seam.

## What I'd improve with more time
- **Eval harness** — a labelled set of requests with expected `action`/`matched_rule`
  and a checker script (the rule engine is pure, so this is cheap and high-value).
- **Async pipeline** — `API Gateway → SQS → Lambda worker → DynamoDB` for durable
  ingestion, retries, and back-pressure; the decision becomes an event others consume.
- **Persistence** — write decisions to DynamoDB (or fan out the audit events) for a
  queryable history and analytics.
- **Tier-based gray-area policy** — use the `tier` field to auto-approve trusted
  customers up to a higher limit instead of blanket-escalating the middle band.
- **Richer PII handling** — field-level encryption at rest + stricter log redaction.
- **Measuring quality in production** — track ESCALATE rate and human-override rate
  per rule, sample APPROVE/REJECT for audit, and alert on distribution drift.
