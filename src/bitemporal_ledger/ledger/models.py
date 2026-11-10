"""Ledger request/result models (M3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class CorrectionRequest:
    """A proposed correction. Never already-accepted."""

    txn_group_id: str
    correction_type: str
    reason_code: str
    reason_note: str
    source_ref: str
    actor_id: str
    recorded_at: datetime
    expected_prior_revision_id: int | None = None
    proposed_amount: Decimal | None = None
    proposed_units: Decimal | None = None
    proposed_effective_date: date | None = None
    proposed_scheme_code: str | None = None


@dataclass(frozen=True)
class CorrectionResult:
    applied: bool
    reason_code: str
    reason: str
    correction_group_id: str | None = None
    revision_id: int | None = None
    revision_no: int | None = None


@dataclass(frozen=True)
class VisibleRevision:
    txn_group_id: str
    txn_revision_id: int
    revision_no: int
    revision_kind: str
    revision_status: str
    txn_type: str
    account_id: int
    instruction_date: date
    effective_date: date
    allotment_date: date | None
    source_nav_date: date | None
    target_allotment_date: date | None
    posting_sequence: int
    scheme_code: str | None
    source_scheme_code: str | None
    target_scheme_code: str | None
    amount_instructed: Decimal | None
    units_instructed: Decimal | None
    recorded_at: datetime


@dataclass(frozen=True)
class IngestReport:
    investors_upserted: int
    accounts_upserted: int
    transactions_created: int
    transactions_skipped: int
    dataset_hash: str
