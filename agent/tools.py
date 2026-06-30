"""The agent's tools: read-only lookups over the provided reference data.

These are the two tools the agent reasons over (`lookup_customer` and
`get_order_history`), plus a small `get_order` helper. Data is loaded from
bundled JSON and cached; swapping this module for a real datastore would not
touch the rest of the pipeline.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from .config import DATA_DIR
from .models import Customer, Order


@lru_cache(maxsize=1)
def _customers() -> dict[str, Customer]:
    raw = json.loads((DATA_DIR / "customers.json").read_text(encoding="utf-8"))
    return {c["id"]: Customer(**c) for c in raw}


@lru_cache(maxsize=1)
def _orders() -> list[Order]:
    raw = json.loads((DATA_DIR / "orders.json").read_text(encoding="utf-8"))
    return [Order(**o) for o in raw]


# --- Tools exposed to the agent -------------------------------------------

def lookup_customer(customer_id: Optional[str]) -> Optional[Customer]:
    """Tool: fetch a customer record by id, or None if not found."""
    if not customer_id:
        return None
    return _customers().get(customer_id)


def get_order_history(customer_id: Optional[str]) -> list[Order]:
    """Tool: return all orders belonging to a customer (possibly empty)."""
    if not customer_id:
        return []
    return [o for o in _orders() if o.customer_id == customer_id]


def get_order(order_id: Optional[str]) -> Optional[Order]:
    """Helper: fetch a single order by id, or None if not found."""
    if not order_id:
        return None
    return next((o for o in _orders() if o.id == order_id), None)


def load_sample_requests() -> list[dict]:
    return json.loads((DATA_DIR / "sample_requests.json").read_text(encoding="utf-8"))
