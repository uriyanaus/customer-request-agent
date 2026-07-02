"""Tiny evaluation harness: labelled requests -> expected (action, matched_rule).

The rule engine is a pure function, so a labelled regression check is cheap and
high-signal. Every case runs in deterministic **mock mode** (no API key, no
network), which is what makes the expected outcomes stable and reproducible.

The suite covers all 12 rule ids plus the documented boundary semantics
($50 strict-under, $500 strict-over).

    python -m evals.run_eval        # from the repo root
    make eval
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from agent.classifier import MockClassifier
from agent.config import Settings
from agent.pipeline import process_request

CASES = Path(__file__).parent / "cases.json"


def main() -> int:
    # Silence the per-decision audit log so eval output stays a clean table.
    logging.getLogger("agent").setLevel(logging.WARNING)

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    settings = Settings(llm_mode="mock")     # pin deterministic mock mode
    classifier = MockClassifier()

    print(f"Running {len(cases)} eval cases (mock mode, today={settings.today})\n")
    print(f"{'id':<6} {'result':<6} {'action':<9} matched_rule")
    print("-" * 56)

    passed = 0
    failures: list[str] = []
    for case in cases:
        decision = process_request(case["text"], settings=settings, classifier=classifier)
        ok = (
            decision.action.value == case["expected_action"]
            and decision.matched_rule == case["expected_rule"]
        )
        if ok:
            passed += 1
        else:
            failures.append(
                f"{case['id']}: expected {case['expected_action']}/{case['expected_rule']}, "
                f"got {decision.action.value}/{decision.matched_rule}"
            )
        print(f"{case['id']:<6} {'PASS' if ok else 'FAIL':<6} "
              f"{decision.action.value:<9} {decision.matched_rule}")

    print("-" * 56)
    print(f"\n{passed}/{len(cases)} passed.")
    if failures:
        print("\nFailures:")
        for line in failures:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
