"""Logical record models for the M2 generator (D-034).

These are instruction-level intents, not ledger-derived facts. Fields named
``generator_estimated_*`` are feasibility estimates computed inside the
generator only; M3 recomputes every derived value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Investor:
    investor_id: int
    synthetic_ref: str
    display_name: str
    data_class: str
    synthetic_label: str

    def to_canonical(self) -> dict:
        return {
            "investor_id": self.investor_id,
            "synthetic_ref": self.synthetic_ref,
            "display_name": self.display_name,
            "data_class": self.data_class,
            "synthetic_label": self.synthetic_label,
        }


@dataclass(frozen=True)
class Account:
    account_id: int
    investor_id: int
    synthetic_ref: str
    display_name: str
    account_status: str
    currency: str
    opened_date: date
    closed_date: date | None
    data_class: str
    synthetic_label: str

    def to_canonical(self) -> dict:
        return {
            "account_id": self.account_id,
            "investor_id": self.investor_id,
            "synthetic_ref": self.synthetic_ref,
            "display_name": self.display_name,
            "account_status": self.account_status,
            "currency": self.currency,
            "opened_date": self.opened_date,
            "closed_date": self.closed_date,
            "data_class": self.data_class,
            "synthetic_label": self.synthetic_label,
        }


@dataclass(frozen=True)
class Transaction:
    txn_group_id: str
    account_id: int
    investor_id: int
    txn_type: str
    instruction_date: date
    effective_date: date
    allotment_date: date | None
    posting_sequence: int
    scheme_code: str | None
    source_scheme_code: str | None
    target_scheme_code: str | None
    amount_instructed: Decimal | None
    units_instructed: Decimal | None
    recorded_at: datetime
    generator_estimated_units: Decimal | None
    generator_estimated_proceeds: Decimal | None
    data_class: str
    synthetic_label: str

    def to_canonical(self) -> dict:
        return {
            "txn_group_id": self.txn_group_id,
            "account_id": self.account_id,
            "investor_id": self.investor_id,
            "txn_type": self.txn_type,
            "instruction_date": self.instruction_date,
            "effective_date": self.effective_date,
            "allotment_date": self.allotment_date,
            "posting_sequence": self.posting_sequence,
            "scheme_code": self.scheme_code,
            "source_scheme_code": self.source_scheme_code,
            "target_scheme_code": self.target_scheme_code,
            "amount_instructed": self.amount_instructed,
            "units_instructed": self.units_instructed,
            "recorded_at": self.recorded_at,
            "generator_estimated_units": self.generator_estimated_units,
            "generator_estimated_proceeds": self.generator_estimated_proceeds,
            "data_class": self.data_class,
            "synthetic_label": self.synthetic_label,
        }


@dataclass(frozen=True)
class CorrectionIntent:
    correction_intent_id: str
    txn_group_id: str
    account_id: int
    correction_type: str
    reason_code: str
    reason_note: str
    proposed_amount: Decimal | None
    proposed_units: Decimal | None
    proposed_scheme_code: str | None
    proposed_effective_date: date | None
    recorded_at: datetime
    actor_id: str
    data_class: str
    synthetic_label: str

    def to_canonical(self) -> dict:
        return {
            "correction_intent_id": self.correction_intent_id,
            "txn_group_id": self.txn_group_id,
            "account_id": self.account_id,
            "correction_type": self.correction_type,
            "reason_code": self.reason_code,
            "reason_note": self.reason_note,
            "proposed_amount": self.proposed_amount,
            "proposed_units": self.proposed_units,
            "proposed_scheme_code": self.proposed_scheme_code,
            "proposed_effective_date": self.proposed_effective_date,
            "recorded_at": self.recorded_at,
            "actor_id": self.actor_id,
            "data_class": self.data_class,
            "synthetic_label": self.synthetic_label,
        }


@dataclass(frozen=True)
class GeneratedDataset:
    investors: list[Investor]
    accounts: list[Account]
    transactions: list[Transaction]
    correction_intents: list[CorrectionIntent]
    manifest: dict
