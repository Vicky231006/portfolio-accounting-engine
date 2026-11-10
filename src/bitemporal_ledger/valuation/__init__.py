"""As-of positions and NAV-based valuation (M4, FR-B5/FR-B6).

Positions are derived by replaying the visible M3 revisions at knowledge
time K (never the current projection). Valuation prices each holding from
an M1 NAV snapshot with the approved stale-carry policy (D-049–D-051).
No return is ever calculated here; that is M5.
"""

from __future__ import annotations
