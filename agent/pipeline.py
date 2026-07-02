"""Orchestration: free text -> AgentDecision.

Wires the stages together (classify -> tools -> rules) and assembles the final
structured decision with a full reasoning trace. This is the cloud-agnostic
entry point shared by the CLI and the Lambda handler.
"""
from __future__ import annotations

from typing import Optional

from .classifier import Classifier, get_classifier
from .config import Settings, load_settings
from .logging_utils import log_decision
from .models import AgentDecision
from .rules import decide
from . import tools


def process_request(
    text: str,
    settings: Optional[Settings] = None,
    classifier: Optional[Classifier] = None,
) -> AgentDecision:
    settings = settings or load_settings()
    classifier = classifier or get_classifier(settings)

    # 1. Understand the request (LLM or mock).
    parsed = classifier.classify(text)
    trace: list[str] = [
        f"Parsed request: type={parsed.request_type.value}, "
        f"customer_id={parsed.customer_id}, order_id={parsed.order_id}, amount={parsed.amount}."
    ]

    # 2. Look up reference data via the tools. The order is resolved through
    #    the customer's own order history (see tools.resolve_order for why the
    #    global fallback exists).
    customer = tools.lookup_customer(parsed.customer_id)
    history = tools.get_order_history(parsed.customer_id)
    order = tools.resolve_order(parsed.order_id, history)
    if parsed.customer_id:
        trace.append(
            f"Tool lookup_customer({parsed.customer_id}) -> "
            f"{'found' if customer else 'not found'}; "
            f"get_order_history -> {len(history)} order(s)."
        )

    # 3. Apply the deterministic rule engine.
    outcome = decide(parsed, customer, order, settings)
    trace.extend(outcome.trace)

    decision = AgentDecision(
        action=outcome.action,
        matched_rule=outcome.matched_rule,
        reasoning=f"{outcome.action.value} via rule '{outcome.matched_rule}'.",
        reasoning_trace=trace,
        request=parsed,
        customer_id=customer.id if customer else parsed.customer_id,
        order_id=order.id if order else parsed.order_id,
        # Report the classifier that actually parsed the request, not the
        # configured mode — they differ when the LLM call fell back to mock,
        # and the audit trail must be truthful exactly in that failure case.
        llm_mode=parsed.parsed_by,
    )

    log_decision(decision)
    return decision
