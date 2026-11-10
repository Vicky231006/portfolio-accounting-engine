"""Generator configuration: typed view of ``config/generator.yaml`` (M2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from bitemporal_ledger.generator.canonical import canonical_hash

APPROVED_TRANSACTION_TYPES = frozenset(
    {"CONTRIBUTION", "WITHDRAWAL", "PURCHASE", "REDEMPTION", "SIP_INSTALMENT", "SWITCH"}
)
APPROVED_CORRECTION_TYPES = frozenset({"REPLACE", "VOID", "REVERSE_AND_REPLACE"})


@dataclass(frozen=True)
class GeneratorConfig:
    version: int
    generator_version: str
    seed: int
    nav_snapshot_id: int
    synthetic_label: str
    disclaimer: str
    investor_count: int
    account_count: int
    account_opening_start: date
    account_opening_end: date
    transaction_end: date
    active_percent: int
    closed_percent: int
    transaction_weights: dict[str, int]
    discretionary_min_per_account: int
    discretionary_max_per_account: int
    sip_schedules_per_account_min: int
    sip_schedules_per_account_max: int
    sip_day_of_month_min: int
    sip_day_of_month_max: int
    sip_schedule_max_months: int
    amount_min: Decimal
    amount_max: Decimal
    withdrawal_min: Decimal
    withdrawal_max: Decimal
    purchase_min: Decimal
    purchase_max: Decimal
    sip_amount_min: Decimal
    sip_amount_max: Decimal
    initial_contribution_min: Decimal
    initial_contribution_max: Decimal
    redeem_fraction_percent_min: int
    redeem_fraction_percent_max: int
    correction_rate_percent: int
    correction_type_weights: dict[str, int]
    backdating_delay_days_min: int
    backdating_delay_days_max: int
    correction_eligible_types: tuple[str, ...]
    synthetic_operator_count: int
    transaction_recorded_hour_utc: int
    transaction_recorded_minute_window: int
    correction_recorded_hour_utc: int
    correction_recorded_minute_window: int
    scheme_pool_min_observations: int
    scheme_pool_min_first_nav_date: date
    scheme_pool_max_paths: int
    rounding_amount_dp: int
    rounding_units_dp: int
    raw: dict

    @classmethod
    def from_yaml(cls, path: str | Path) -> GeneratorConfig:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(document)

    @classmethod
    def from_mapping(cls, document: dict) -> GeneratorConfig:
        status = document.get("account_status_mix", {})
        weights = {str(k): int(v) for k, v in document["transaction_weights"].items()}
        _validate_weights(weights)
        correction_weights = {
            str(k): int(v) for k, v in document["correction_type_weights"].items()
        }
        _validate_weights(correction_weights)
        eligible = tuple(str(t) for t in document["correction_eligible_types"])
        for txn_type in eligible:
            if txn_type not in APPROVED_TRANSACTION_TYPES:
                raise ValueError(f"Unapproved correction-eligible type: {txn_type!r}")
        rounding = document.get("rounding", {})
        if rounding.get("units_mode") != "ROUND_DOWN" or rounding.get("amount_mode") != "ROUND_HALF_UP":
            raise ValueError("Rounding modes must match D-026 (units ROUND_DOWN, amounts ROUND_HALF_UP)")
        return cls(
            version=int(document["version"]),
            generator_version=str(document["generator_version"]),
            seed=int(document["seed"]),
            nav_snapshot_id=int(document["nav_snapshot_id"]),
            synthetic_label=str(document["synthetic_label"]),
            disclaimer=str(document["disclaimer"]),
            investor_count=int(document["investor_count"]),
            account_count=int(document["account_count"]),
            account_opening_start=date.fromisoformat(str(document["account_opening_start"])),
            account_opening_end=date.fromisoformat(str(document["account_opening_end"])),
            transaction_end=date.fromisoformat(str(document["transaction_end"])),
            active_percent=int(status["ACTIVE"]),
            closed_percent=int(status["CLOSED"]),
            transaction_weights=weights,
            discretionary_min_per_account=int(document["discretionary_min_per_account"]),
            discretionary_max_per_account=int(document["discretionary_max_per_account"]),
            sip_schedules_per_account_min=int(document["sip_schedules_per_account_min"]),
            sip_schedules_per_account_max=int(document["sip_schedules_per_account_max"]),
            sip_day_of_month_min=int(document["sip_day_of_month_min"]),
            sip_day_of_month_max=int(document["sip_day_of_month_max"]),
            sip_schedule_max_months=int(document["sip_schedule_max_months"]),
            amount_min=Decimal(str(document["amount_min"])),
            amount_max=Decimal(str(document["amount_max"])),
            withdrawal_min=Decimal(str(document["withdrawal_min"])),
            withdrawal_max=Decimal(str(document["withdrawal_max"])),
            purchase_min=Decimal(str(document["purchase_min"])),
            purchase_max=Decimal(str(document["purchase_max"])),
            sip_amount_min=Decimal(str(document["sip_amount_min"])),
            sip_amount_max=Decimal(str(document["sip_amount_max"])),
            initial_contribution_min=Decimal(str(document["initial_contribution_min"])),
            initial_contribution_max=Decimal(str(document["initial_contribution_max"])),
            redeem_fraction_percent_min=int(document["redeem_fraction_percent_min"]),
            redeem_fraction_percent_max=int(document["redeem_fraction_percent_max"]),
            correction_rate_percent=int(document["correction_rate_percent"]),
            correction_type_weights=correction_weights,
            backdating_delay_days_min=int(document["backdating_delay_days_min"]),
            backdating_delay_days_max=int(document["backdating_delay_days_max"]),
            correction_eligible_types=eligible,
            synthetic_operator_count=int(document["synthetic_operator_count"]),
            transaction_recorded_hour_utc=int(document["transaction_recorded_hour_utc"]),
            transaction_recorded_minute_window=int(document["transaction_recorded_minute_window"]),
            correction_recorded_hour_utc=int(document["correction_recorded_hour_utc"]),
            correction_recorded_minute_window=int(document["correction_recorded_minute_window"]),
            scheme_pool_min_observations=int(document["scheme_pool_min_observations"]),
            scheme_pool_min_first_nav_date=date.fromisoformat(str(document["scheme_pool_min_first_nav_date"])),
            scheme_pool_max_paths=int(document["scheme_pool_max_paths"]),
            rounding_amount_dp=int(rounding["amount_dp"]),
            rounding_units_dp=int(rounding["units_dp"]),
            raw=document,
        )

    def config_hash(self) -> str:
        """SHA-256 of the canonical serialisation of the parsed config."""
        return canonical_hash(self.raw)


def _validate_weights(weights: dict[str, int]) -> None:
    if not weights:
        raise ValueError("Weight map must not be empty")
    if sum(weights.values()) != 100:
        raise ValueError(f"Weights must sum to 100, got {sum(weights.values())}")
    for key in weights:
        if key not in APPROVED_TRANSACTION_TYPES and key not in APPROVED_CORRECTION_TYPES:
            raise ValueError(f"Unapproved type in weights: {key!r}")
