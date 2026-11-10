"""Immutable transaction revision ledger and bitemporal corrections (M3).

Implements PRD FR-B3/FR-B4. See ``docs/M3_DESIGN.md`` and DECISIONS D-041
to D-045. M3 never values portfolios or calculates returns.
"""

from __future__ import annotations
