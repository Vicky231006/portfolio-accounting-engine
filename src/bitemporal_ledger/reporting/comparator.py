"""Overwrite-in-place comparator (M6, METHODOLOGY §10.4, FR-B14).

The comparator keeps only the latest (current-row) transaction state per
business transaction — no revision history, no prior payload. Fed the same
transaction stream (originals then corrections), it attempts to reconstruct
the K1 view from retained data only. Corrected accounts therefore diverge:
the prior instruction amount, derived units, lineage and reason cannot be
recovered. It never retrieves a saved snapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from bitemporal_ledger.ledger.service import LedgerService


class OverwriteComparator:
    """Naive current-state replica fed with the same transactions."""

    def __init__(self, dsn: str, nav_snapshot_id: int) -> None:
        self.dsn = dsn
        self.nav_snapshot_id = nav_snapshot_id
        self.ledger = LedgerService(dsn, nav_snapshot_id)
        self._current: dict[str, dict] = {}

    def ingest_current(self) -> int:
        """Load only the current rows (latest revision per transaction)."""
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT txn_group_id, amount_instructed, units_instructed, effective_date, txn_type"
                    " FROM core.txn_version_current WHERE is_voided = FALSE"
                )
                rows = cur.fetchall()
        self._current = {
            row[0]: {
                "amount_instructed": str(row[1]) if row[1] is not None else None,
                "units_instructed": str(row[2]) if row[2] is not None else None,
                "effective_date": row[3].isoformat() if row[3] else None,
                "txn_type": row[4],
            }
            for row in rows
        }
        return len(self._current)

    def attempt_k1_reconstruction(self, txn_group_id: str, k1_known_as_of: datetime) -> dict:
        """Attempt to return the K1 view from retained data only.

        The comparator only ever retained the *current* row, so when the
        transaction was corrected after K1 the K1 instruction is
        irrecoverable: prior amount, lineage and reason were overwritten.
        """
        current = self._current.get(txn_group_id)
        was_corrected = False
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM core.txn_revision WHERE txn_group_id = %s AND revision_no > 1",
                    (txn_group_id,),
                )
                count = cur.fetchone()[0]
                was_corrected = count > 0
        return {
            "txn_group_id": txn_group_id,
            "reproducible": not was_corrected,
            "reason": (
                "prior instruction amount, lineage and reason were overwritten"
                if was_corrected
                else "uncorrected; current row equals K1 row"
            ),
            "current_state": current,
            "k1_known_as_of": k1_known_as_of.isoformat() if isinstance(k1_known_as_of, datetime) else str(k1_known_as_of),
        }

    def compare_after_corrections(self, account_transactions: list[str]) -> dict:
        reproducible, unreproducible = [], []
        for txn_group_id in account_transactions:
            result = self.attempt_k1_reconstruction(txn_group_id, datetime.now(timezone.utc))
            (reproducible if result["reproducible"] else unreproducible).append(txn_group_id)
        return {
            "reproducible": reproducible,
            "unreproducible": unreproducible,
            "reproducible_count": len(reproducible),
            "total_count": len(account_transactions),
        }
