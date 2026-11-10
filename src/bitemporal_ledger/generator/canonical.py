"""Canonical logical-record serialisation and SHA-256 (M2, D-035).

The canonical form is the only input to a record hash: sorted keys,
compact separators, decimals rendered as fixed strings, datetimes rendered
as UTC ISO-8601 with a ``Z`` suffix. Pretty-printed JSON is never hashed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

_CANONICAL_SEPARATORS = (",", ":")


def canonical_bytes(value: Any) -> bytes:
    """Serialise a primitive-only value to its canonical byte form."""
    return json.dumps(
        _to_primitives(value), sort_keys=True, separators=_CANONICAL_SEPARATORS
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    """SHA-256 hex digest of the canonical serialisation."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def dataset_hash(record_hashes: list[str]) -> str:
    """SHA-256 over the ordered sequence of per-record hashes."""
    return hashlib.sha256("".join(record_hashes).encode("ascii")).hexdigest()


def _to_primitives(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return _to_utc_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_primitives(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_primitives(v) for v in value]
    raise TypeError(f"Canonical hashing does not support type {type(value)!r}")


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
