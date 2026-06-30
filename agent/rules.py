"""Deterministic decision engine.

This is the part that actually decides APPROVE / REJECT / ESCALATE. It is a
pure function of (parsed request, resolved customer, resolved order, settings)
so the money decision is auditable and unit-testable — the LLM never makes the
final call. Rules are evaluated in a fixed precedence order; the first match
wins and every step is appended to a human-readable trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import Settings
from .models import Action, Customer, Order, ParsedRequest, RequestType

# Order states we consider eligible for an automated refund decision.
REFUNDABLE_ORDER_STATUSES = {"completed", "shipped", "delivered"}


@dataclass
class RuleOutcome:
    action: Action
    matched_rule: str
    trace: list[str] = field(default_factory=list)


def decide(
    parsed: ParsedRequest,
    customer: Optional[Customer],
    order: Optional[Order],
    settings: Settings,
) -> RuleOutcome:
    trace: list[str] = []

    # 1. Only refunds have an automated path; other intents route to a human.
    if parsed.request_type != RequestType.REFUND:
        trace.append(f"Request type is {parsed.request_type.value}; no automated refund rule applies.")
        return RuleOutcome(Action.ESCALATE, "non_refund_request", trace)

    # 2. Incomplete / ambiguous request -> cannot act safely (ESCALATE).
    missing = list(parsed.missing_fields)
    for name, value in (("customer_id", parsed.customer_id),
                        ("order_id", parsed.order_id),
                        ("amount", parsed.amount)):
        if value in (None, "") and name not in missing:
            missing.append(name)
    if missing:
        trace.append(f"Missing key information: {', '.join(missing)}.")
        return RuleOutcome(Action.ESCALATE, "incomplete_request", trace)

    # 3. Entity resolution failures -> REJECT.
    if customer is None:
        trace.append(f"No customer found for id {parsed.customer_id}.")
        return RuleOutcome(Action.REJECT, "no_matching_customer", trace)
    trace.append(f"Resolved customer {customer.id} (tier={customer.tier}, status={customer.status}).")

    if order is None:
        trace.append(f"No order {parsed.order_id} found.")
        return RuleOutcome(Action.REJECT, "no_matching_order", trace)
    if order.customer_id != customer.id:
        trace.append(f"Order {order.id} does not belong to customer {customer.id}.")
        return RuleOutcome(Action.REJECT, "order_customer_mismatch", trace)
    trace.append(f"Resolved order {order.id} (amount=${order.amount:.2f}, date={order.date}, status={order.status}).")

    # 4. Account / order-state edge cases (documented rule extensions).
    if customer.status != "active":
        trace.append(f"Customer status is '{customer.status}', not active.")
        return RuleOutcome(Action.ESCALATE, "customer_not_active", trace)
    if order.status not in REFUNDABLE_ORDER_STATUSES:
        trace.append(f"Order status '{order.status}' is not normally refundable.")
        return RuleOutcome(Action.ESCALATE, "order_not_refundable", trace)
    if parsed.amount > order.amount:
        trace.append(f"Requested refund ${parsed.amount:.2f} exceeds order total ${order.amount:.2f}.")
        return RuleOutcome(Action.ESCALATE, "refund_exceeds_order_total", trace)

    # 5. Core business thresholds.
    age_days = (settings.today - order.date).days
    trace.append(f"Order age is {age_days} days as of {settings.today}.")

    if parsed.amount > settings.escalate_min_amount:
        trace.append(f"Refund ${parsed.amount:.2f} is over the ${settings.escalate_min_amount:.0f} threshold.")
        return RuleOutcome(Action.ESCALATE, "amount_over_500", trace)
    if age_days > settings.escalate_min_age_days:
        trace.append(f"Order is older than {settings.escalate_min_age_days} days.")
        return RuleOutcome(Action.ESCALATE, "order_older_than_90d", trace)

    if parsed.amount < settings.approve_max_amount and age_days <= settings.approve_max_age_days:
        trace.append(f"Refund is under ${settings.approve_max_amount:.0f} and order within {settings.approve_max_age_days} days.")
        return RuleOutcome(Action.APPROVE, "under_50_within_30d", trace)

    # 6. Gray band: no auto-approve and no hard-escalate trigger -> human review.
    trace.append("Falls in the gray band (not auto-approvable, no hard-escalate trigger); routing to human review.")
    return RuleOutcome(Action.ESCALATE, "gray_area_review", trace)
