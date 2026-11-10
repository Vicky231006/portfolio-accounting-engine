"""Determinism property tests for the M2 generator (FR-B1, E7)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from bitemporal_ledger.generator.canonical import canonical_bytes, canonical_hash
from bitemporal_ledger.generator.config import GeneratorConfig
from bitemporal_ledger.generator.generator import SyntheticGenerator
from bitemporal_ledger.generator.nav_index import NavIndex


def _nav_index() -> NavIndex:
    mapping: dict[str, list[tuple[date, Decimal]]] = {}
    for code, base in (("119436", "15"), ("119528", "25"), ("119620", "35")):
        start = date(2021, 1, 1)
        mapping[code] = [
            (start.fromordinal(start.toordinal() + day), Decimal(base) + Decimal(day % 30) / Decimal("10"))
            for day in range(0, 365 * 2)
        ]
    return NavIndex.from_mapping(mapping)


def _config(seed: int) -> GeneratorConfig:
    return GeneratorConfig.from_mapping(
        {
            "version": 1,
            "generator_version": "generator-property-1.0.0",
            "seed": seed,
            "nav_snapshot_id": 3,
            "synthetic_label": "synthetic_accounts_real_nav",
            "disclaimer": "Synthetic property test disclaimer.",
            "investor_count": 2,
            "account_count": 3,
            "account_opening_start": "2021-01-01",
            "account_opening_end": "2021-06-01",
            "transaction_end": "2022-12-31",
            "account_status_mix": {"ACTIVE": 100, "CLOSED": 0},
            "transaction_weights": {
                "CONTRIBUTION": 10,
                "WITHDRAWAL": 8,
                "PURCHASE": 30,
                "REDEMPTION": 12,
                "SIP_INSTALMENT": 25,
                "SWITCH": 15,
            },
            "discretionary_min_per_account": 8,
            "discretionary_max_per_account": 12,
            "sip_schedules_per_account_min": 1,
            "sip_schedules_per_account_max": 1,
            "sip_day_of_month_min": 5,
            "sip_day_of_month_max": 5,
            "sip_schedule_max_months": 12,
            "amount_min": "5000.00",
            "amount_max": "40000.00",
            "withdrawal_min": "2000.00",
            "withdrawal_max": "15000.00",
            "purchase_min": "5000.00",
            "purchase_max": "40000.00",
            "sip_amount_min": "5000.00",
            "sip_amount_max": "15000.00",
            "initial_contribution_min": "50000.00",
            "initial_contribution_max": "80000.00",
            "redeem_fraction_percent_min": 10,
            "redeem_fraction_percent_max": 50,
            "correction_rate_percent": 20,
            "correction_type_weights": {"REPLACE": 60, "VOID": 20, "REVERSE_AND_REPLACE": 20},
            "backdating_delay_days_min": 1,
            "backdating_delay_days_max": 30,
            "correction_eligible_types": ["PURCHASE"],
            "synthetic_operator_count": 3,
            "transaction_recorded_hour_utc": 18,
            "transaction_recorded_minute_window": 120,
            "correction_recorded_hour_utc": 11,
            "correction_recorded_minute_window": 240,
            "scheme_pool_min_observations": 750,
            "scheme_pool_min_first_nav_date": "2014-01-01",
            "scheme_pool_max_paths": 30,
            "rounding": {"amount_dp": 2, "units_dp": 3, "units_mode": "ROUND_DOWN", "amount_mode": "ROUND_HALF_UP"},
        }
    )


def test_two_clean_runs_are_byte_identical() -> None:
    nav_index = _nav_index()
    first = SyntheticGenerator(_config(seed=20261109), nav_index).generate()
    second = SyntheticGenerator(_config(seed=20261109), nav_index).generate()

    first_bytes = [canonical_bytes(txn.to_canonical()) for txn in first.transactions]
    second_bytes = [canonical_bytes(txn.to_canonical()) for txn in second.transactions]
    assert first_bytes == second_bytes
    assert canonical_hash(first.manifest) == canonical_hash(second.manifest)
    assert first.manifest["hashes"]["dataset"] == second.manifest["hashes"]["dataset"]


def test_dataset_hash_equals_joined_record_hashes() -> None:
    nav_index = _nav_index()
    dataset = SyntheticGenerator(_config(seed=7), nav_index).generate()
    expected = dataset.manifest["hashes"]["dataset"]
    record_hashes = [
        canonical_hash(inv.to_canonical()) for inv in dataset.investors
    ] + [canonical_hash(acc.to_canonical()) for acc in dataset.accounts] + [
        canonical_hash(txn.to_canonical()) for txn in dataset.transactions
    ] + [canonical_hash(intent.to_canonical()) for intent in dataset.correction_intents]
    import hashlib

    assert hashlib.sha256("".join(record_hashes).encode("ascii")).hexdigest() == expected
