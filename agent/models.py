"""Pydantic models: the typed contract between every stage of the pipeline."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Action(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class RequestType(str, Enum):
    REFUND = "REFUND"
    ACCOUNT_QUESTION = "ACCOUNT_QUESTION"
    COMPLAINT = "COMPLAINT"
    UNKNOWN = "UNKNOWN"


class Customer(BaseModel):
    id: str
    name: str
    email: str
    tier: str
    status: str


class Order(BaseModel):
    id: str
    customer_id: str
    amount: float
    date: date
    status: str


class ParsedRequest(BaseModel):
    """Structured view of the free-text request, produced by the classifier."""

    raw_text: str
    request_type: RequestType = RequestType.UNKNOWN
    customer_id: Optional[str] = None
    order_id: Optional[str] = None
    amount: Optional[float] = None
    missing_fields: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    # Which classifier actually produced this parse. Distinct from the
    # *configured* mode: the LLM classifier falls back to the mock on failure,
    # and the audit trail must reflect what really ran. Required and
    # Literal-typed on purpose — a classifier that forgets to set it fails at
    # construction instead of silently mislabelling the audit trail. The
    # free-text `notes` is human-readable detail; this is the canonical label.
    parsed_by: Literal["anthropic", "mock"]


class AgentDecision(BaseModel):
    """Final structured output of the agent (the deliverable schema).

    Deliberately carries no PII (no name/email) — only the ids needed to
    audit the decision.
    """

    action: Action
    matched_rule: str
    reasoning: str
    reasoning_trace: list[str] = Field(default_factory=list)
    request: ParsedRequest
    customer_id: Optional[str] = None
    order_id: Optional[str] = None
    # The classifier that actually parsed this request ("anthropic" | "mock"),
    # not the configured mode — they differ when the LLM call fell back.
    llm_mode: str = "mock"
