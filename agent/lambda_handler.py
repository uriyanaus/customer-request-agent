"""AWS Lambda adapter: API Gateway (HTTP API) -> Lambda -> JSON decision.

The core agent is cloud-agnostic; this is a thin translation layer between an
API Gateway proxy event and `process_request`. Swapping to an async SQS-consumer
adapter later would not touch the agent itself.

Request:  POST /decisions   { "request": "<free text>" }
Response: 200               <AgentDecision as JSON>
"""
from __future__ import annotations

import base64
import json

from .pipeline import process_request


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event: dict, context=None) -> dict:
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        request_text = (payload or {}).get("request")
        if not request_text:
            return _response(400, {"error": "missing 'request' field"})

        decision = process_request(request_text)
        return _response(200, decision.model_dump(mode="json"))
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid JSON body"})
    except Exception as exc:  # never leak a stack trace to the caller
        return _response(500, {"error": "internal error", "detail": type(exc).__name__})
