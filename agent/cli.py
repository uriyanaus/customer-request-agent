"""Command-line entry point (the local 'single documented command').

    python -m agent.cli "Refund for ORD1001, this is CUST001. It was $30."
    python -m agent.cli --samples        # run all bundled sample requests
"""
from __future__ import annotations

import argparse
import json

from .models import AgentDecision
from .pipeline import process_request
from .tools import load_sample_requests


def _dump(decision: AgentDecision) -> str:
    return json.dumps(decision.model_dump(mode="json"), indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous customer-request agent")
    parser.add_argument("request", nargs="?", help="Free-text customer request")
    parser.add_argument("--samples", action="store_true", help="Run all bundled sample requests")
    args = parser.parse_args(argv)

    if args.samples:
        for sample in load_sample_requests():
            print(f"\n=== {sample['id']}: {sample['text']}")
            print(_dump(process_request(sample["text"])))
        return 0

    if not args.request:
        parser.error("provide a request string, or use --samples")

    print(_dump(process_request(args.request)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
