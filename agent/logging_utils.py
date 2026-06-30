"""Minimal structured logging with PII redaction.

A stateless service still needs an audit trail: each decision is emitted as a
single JSON event to stderr (-> CloudWatch under Lambda). Email local-parts are
redacted so customer PII never lands in logs.
"""
from __future__ import annotations

import json
import logging
import re
import sys

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[^\s]+)")


def redact_pii(text: str) -> str:
    """Mask email local-parts, e.g. alice@example.com -> a***@example.com."""
    return _EMAIL_RE.sub(r"\1***\2", text)


def get_logger(name: str = "agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_decision(decision) -> None:
    """Emit one PII-redacted JSON audit event per decision."""
    event = {
        "event": "decision",
        "action": decision.action.value,
        "matched_rule": decision.matched_rule,
        "request_type": decision.request.request_type.value,
        "customer_id": decision.customer_id,
        "order_id": decision.order_id,
        "llm_mode": decision.llm_mode,
    }
    get_logger().info(redact_pii(json.dumps(event, ensure_ascii=False)))
