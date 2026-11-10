"""Reporting canonical payload (M6, METHODOLOGY §10)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from bitemporal_ledger.generator.canonical import canonical_hash


def canonical_payload_bytes(payload: dict) -> bytes:
    return json.dumps(_primitives(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_payload_hash(payload: dict) -> str:
    return canonical_hash(_primitives(payload))


def _primitives(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(value, "hour") else value.isoformat()
    if isinstance(value, dict):
        return {str(k): _primitives(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitives(v) for v in value]
    raise TypeError(f"Cannot canonicalise {type(value)!r}")
