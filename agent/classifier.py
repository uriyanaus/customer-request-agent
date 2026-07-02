"""Request understanding: turn free text into a ParsedRequest.

Two interchangeable implementations behind one interface:
  - AnthropicClassifier : uses Claude structured output for NLU.
  - MockClassifier      : deterministic regex/keyword extraction; no API key.

The classifier only *understands* the request (extract fields, classify intent).
It never decides the outcome — that is the rule engine's job. Keeping the LLM
out of the money decision is what makes the system auditable and testable.
"""
from __future__ import annotations

import re
from typing import Optional, Protocol

from pydantic import BaseModel

from .config import Settings
from .logging_utils import get_logger
from .models import ParsedRequest, RequestType

logger = get_logger()


class Classifier(Protocol):
    def classify(self, text: str) -> ParsedRequest: ...


# --- Deterministic / mock extractor (also serves as the "regex gate") -------

_CUSTOMER_RE = re.compile(r"\bCUST\d{3,}\b", re.IGNORECASE)
_ORDER_RE = re.compile(r"\bORD\d{3,}\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)")

_REFUND_KW = ("refund", "money back", "reimburse", "chargeback")
_ACCOUNT_KW = ("account", "password", "email on file", "change my", "update my", "log in", "login")
_COMPLAINT_KW = ("complaint", "unhappy", "disappointed", "broken", "damaged", "terrible")


def _keyword_request_type(text: str) -> RequestType:
    t = text.lower()
    if any(k in t for k in _REFUND_KW):
        return RequestType.REFUND
    if any(k in t for k in _ACCOUNT_KW):
        return RequestType.ACCOUNT_QUESTION
    if any(k in t for k in _COMPLAINT_KW):
        return RequestType.COMPLAINT
    return RequestType.UNKNOWN


class MockClassifier:
    """Regex + keyword extraction. Deterministic, offline, free."""

    def classify(self, text: str) -> ParsedRequest:
        cust = _CUSTOMER_RE.search(text)
        order = _ORDER_RE.search(text)
        amount_m = _AMOUNT_RE.search(text)
        return ParsedRequest(
            raw_text=text,
            request_type=_keyword_request_type(text),
            customer_id=cust.group(0).upper() if cust else None,
            order_id=order.group(0).upper() if order else None,
            amount=float(amount_m.group(1)) if amount_m else None,
            notes="parsed by mock (regex) classifier",
            parsed_by="mock",
        )


# --- Anthropic-backed extractor --------------------------------------------

class _LLMExtraction(BaseModel):
    """Schema the LLM fills in (drives structured output)."""

    request_type: RequestType
    customer_id: Optional[str] = None
    order_id: Optional[str] = None
    amount: Optional[float] = None


_SYSTEM = """You extract structured fields from a single customer-service request.
Only return values that are explicitly present in the text — never guess.
- request_type: REFUND, ACCOUNT_QUESTION, COMPLAINT, or UNKNOWN.
- customer_id / order_id: copy identifiers verbatim if present (e.g. CUST001, ORD1001), else null.
- amount: the dollar figure the customer refers to, as a number, else null."""


class AnthropicClassifier:
    """Uses Claude structured output to extract fields, with a mock fallback."""

    def __init__(self, settings: Settings):
        import anthropic  # imported lazily so mock mode needs no dependency

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self._fallback = MockClassifier()

    def classify(self, text: str) -> ParsedRequest:
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=1024,
                system=_SYSTEM,
                messages=[{"role": "user", "content": text}],
                output_format=_LLMExtraction,
            )
            extracted = response.parsed_output
            if extracted is None:
                raise ValueError("no parsed_output returned")
            return ParsedRequest(
                raw_text=text,
                request_type=extracted.request_type,
                customer_id=extracted.customer_id or None,
                order_id=extracted.order_id or None,
                amount=extracted.amount,
                notes=f"parsed by Claude ({self._model})",
                parsed_by="anthropic",
            )
        except Exception as exc:  # robustness: never let the LLM break the pipeline
            logger.info('{"event":"classifier_fallback","error":"%s"}' % type(exc).__name__)
            return self._fallback.classify(text)  # carries parsed_by="mock"


def get_classifier(settings: Settings) -> Classifier:
    if settings.resolved_llm_mode() == "anthropic":
        return AnthropicClassifier(settings)
    return MockClassifier()
