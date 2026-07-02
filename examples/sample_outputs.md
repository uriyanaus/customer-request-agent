# Example inputs & outputs

The 10 bundled sample requests (`agent/data/sample_requests.json`) run through the
agent. Reproduce all of them with:

```bash
make samples        # (deterministic mock mode — no API key needed)
```

## Summary

| Req | Input (abridged) | Decision | Rule |
|---|---|---|---|
| REQ01 | Alice (CUST001), refund ORD1001, $30, 15 days old | **APPROVE** | `under_50_within_30d` |
| REQ02 | CUST002, refund ORD1002, $600 | **ESCALATE** | `amount_over_500` |
| REQ03 | CUST003, refund ORD1003, $120, placed in February (135d) | **ESCALATE** | `order_older_than_90d` |
| REQ04 | CUST001, refund ORD1004, $75, 14 days old | **ESCALATE** | `gray_area_review` |
| REQ05 | CUST999 (unknown), refund ORD5555, $20 | **REJECT** | `no_matching_customer` |
| REQ06 | "I'm really unhappy and I want a refund." (no details) | **ESCALATE** | `incomplete_request` |
| REQ07 | CUST002, refund ORD1005, $45, 57 days old | **ESCALATE** | `gray_area_review` |
| REQ08 | "can CUST005 change the email on file?" | **ESCALATE** | `non_refund_request` |
| REQ09 | CUST004 (suspended), refund ORD1007, $50 | **ESCALATE** | `customer_not_active` |
| REQ10 | CUST003, refund ORD1008, $950, order cancelled | **ESCALATE** | `order_not_refundable` |

Note REQ04 and REQ07 are the deliberate **gray-area** cases (between the $50 and
$500 thresholds, or under $50 but outside the 30-day window) — neither matches an
auto-approve or hard-escalate rule, so both route to human review.

## Full outputs (representative)

### REQ01 — APPROVE (the one clean auto-approve)
```json
{
  "action": "APPROVE",
  "matched_rule": "under_50_within_30d",
  "reasoning": "APPROVE via rule 'under_50_within_30d'.",
  "reasoning_trace": [
    "Parsed request: type=REFUND, customer_id=CUST001, order_id=ORD1001, amount=30.0.",
    "Tool lookup_customer(CUST001) -> found; get_order_history -> 2 order(s).",
    "Resolved customer CUST001 (tier=premium, status=active).",
    "Resolved order ORD1001 (amount=$30.00, date=2026-06-01, status=completed).",
    "Order age is 15 days as of 2026-06-16.",
    "Refund is under $50 and order within 30 days."
  ],
  "request": {
    "raw_text": "Hi, this is Alice (CUST001). I'd like a refund for order ORD1001, it arrived damaged. It was $30.",
    "request_type": "REFUND", "customer_id": "CUST001", "order_id": "ORD1001",
    "amount": 30.0, "missing_fields": [], "notes": "parsed by mock (regex) classifier", "parsed_by": "mock"
  },
  "customer_id": "CUST001", "order_id": "ORD1001", "llm_mode": "mock"
}
```

### REQ04 — ESCALATE (gray area: $75 within 30 days)
```json
{
  "action": "ESCALATE",
  "matched_rule": "gray_area_review",
  "reasoning": "ESCALATE via rule 'gray_area_review'.",
  "reasoning_trace": [
    "Parsed request: type=REFUND, customer_id=CUST001, order_id=ORD1004, amount=75.0.",
    "Tool lookup_customer(CUST001) -> found; get_order_history -> 2 order(s).",
    "Resolved customer CUST001 (tier=premium, status=active).",
    "Resolved order ORD1004 (amount=$75.00, date=2026-06-02, status=completed).",
    "Order age is 14 days as of 2026-06-16.",
    "Falls in the gray band (not auto-approvable, no hard-escalate trigger); routing to human review."
  ],
  "request": {
    "raw_text": "Refund please for ORD1004, this is CUST001. I was charged $75.",
    "request_type": "REFUND", "customer_id": "CUST001", "order_id": "ORD1004",
    "amount": 75.0, "missing_fields": [], "notes": "parsed by mock (regex) classifier", "parsed_by": "mock"
  },
  "customer_id": "CUST001", "order_id": "ORD1004", "llm_mode": "mock"
}
```

### REQ05 — REJECT (no matching customer)
```json
{
  "action": "REJECT",
  "matched_rule": "no_matching_customer",
  "reasoning": "REJECT via rule 'no_matching_customer'.",
  "reasoning_trace": [
    "Parsed request: type=REFUND, customer_id=CUST999, order_id=ORD5555, amount=20.0.",
    "Tool lookup_customer(CUST999) -> not found; get_order_history -> 0 order(s).",
    "No customer found for id CUST999."
  ],
  "request": {
    "raw_text": "Hello, I'm CUST999 and I want my money back for order ORD5555 ($20).",
    "request_type": "REFUND", "customer_id": "CUST999", "order_id": "ORD5555",
    "amount": 20.0, "missing_fields": [], "notes": "parsed by mock (regex) classifier", "parsed_by": "mock"
  },
  "customer_id": "CUST999", "order_id": "ORD5555", "llm_mode": "mock"
}
```

### REQ06 — ESCALATE (incomplete request)
```json
{
  "action": "ESCALATE",
  "matched_rule": "incomplete_request",
  "reasoning": "ESCALATE via rule 'incomplete_request'.",
  "reasoning_trace": [
    "Parsed request: type=REFUND, customer_id=None, order_id=None, amount=None.",
    "Missing key information: customer_id, order_id, amount."
  ],
  "request": {
    "raw_text": "I'm really unhappy and I want a refund.",
    "request_type": "REFUND", "customer_id": null, "order_id": null,
    "amount": null, "missing_fields": [], "notes": "parsed by mock (regex) classifier", "parsed_by": "mock"
  },
  "customer_id": null, "order_id": null, "llm_mode": "mock"
}
```
