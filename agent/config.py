"""Configuration and business-rule thresholds.

Everything that the rules depend on (the 'current' date, dollar/time
thresholds, LLM selection) lives here so the decision logic stays pure and
testable. In particular `today` is injected rather than read from the system
clock, as the assignment fixes it at 2026-06-16.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load_dotenv(path: Path = Path(__file__).parent.parent / ".env") -> None:
    """Minimal .env support (KEY=VALUE lines) so local runs can keep the API key
    out of shell history. Real environment variables always win. Stdlib-only on
    purpose — python-dotenv would be the choice once config grows beyond this.
    Must run before Settings is defined, as its defaults read the environment.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

# The assignment pins "today" so all date-based rules are deterministic.
TODAY = date(2026, 6, 16)


@dataclass(frozen=True)
class Settings:
    today: date = TODAY

    # Business-rule thresholds. Boundary semantics (documented in the README):
    #   approve  : amount STRICTLY under $50  AND age <= 30 days
    #   escalate : amount STRICTLY over  $500 OR  age >  90 days
    approve_max_amount: float = 50.0
    escalate_min_amount: float = 500.0
    approve_max_age_days: int = 30
    escalate_min_age_days: int = 90

    # LLM selection. `auto` uses Anthropic when an API key is present, else mock.
    # Haiku 4.5 is the cheap/fast default for extraction; the LLM only parses the
    # request — it never decides the outcome — so a small model is appropriate.
    # Override with AGENT_MODEL (e.g. claude-sonnet-4-6) for higher extraction accuracy.
    llm_mode: str = os.getenv("AGENT_LLM", "auto")  # auto | anthropic | mock
    anthropic_model: str = os.getenv("AGENT_MODEL", "claude-haiku-4-5")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")

    def resolved_llm_mode(self) -> str:
        if self.llm_mode != "auto":
            return self.llm_mode
        return "anthropic" if self.anthropic_api_key else "mock"


def load_settings() -> Settings:
    return Settings()
