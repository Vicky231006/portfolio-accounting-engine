"""Tests for the deterministic M2 generator (FR-B1, D-034–D-039)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from bitemporal_ledger.generator.canonical import canonical_bytes, canonical_hash
from bitemporal_ledger.generator.config import GeneratorConfig
from bitemporal_ledger.generator.generator import SyntheticGenerator
from bitemporal_ledger.generator.nav_index import NavIndex


def _nav_index() -> NavIndex:
    scheme_a, scheme_b, scheme_c = "119436", "119528", "119620"
    mapping: dict[str, list[tuple[date, Decimal]]] = {code: [] for code in (scheme_a, scheme_b, scheme_c)}
    start = date(2020, 1, 1)
    for day in range(0, 365 * 3):
        nav_date = start.fromordinal(start.toordinal() + day)
        mapping[scheme_a].append((nav_date, Decimal("10") + Decimal(day % 50) / Decimal("10")))
        mapping[scheme_b].append((nav_date, Decimal("20") + Decimal(day % 40) / Decimal("10")))
        mapping[scheme_c].append((nav_date, Decimal("30") + Decimal(day % 30) / Decimal("10")))
    return NavIndex.from_mapping(mapping)


def _config(tmp_path, **overrides):
    document = {
        "version": 1,
        "generator_version": "generator-test-1.0.0",
        "seed": 42,
        "nav_snapshot_id": 3,
        "synthetic_label": "synthetic_accounts_real_nav",
        "disclaimer": "Synthetic test disclaimer.",
        "investor_count": 3,
        "account_count": 4,
        "account_opening_start": "2020-01-01",
        "account_opening_end": "2020-03-01",
        "transaction_end": "2021-12-31",
        "account_status_mix": {"ACTIVE": 85, "CLOSED": 15},
        "transaction_weights": {
            "CONTRIBUTION": 10,
            "WITHDRAWAL": 8,
            "PURCHASE": 30,
            "REDEMPTION": 12,
            "SIP_INSTALMENT": 25,
            "SWITCH": 15,
        },
        "discretionary_min_per_account": 10,
        "discretionary_max_per_account": 20,
        "sip_schedules_per_account_min": 1,
        "sip_schedules_per_account_max": 2,
        "sip_day_of_month_min": 1,
        "sip_day_of_month_max": 28,
        "sip_schedule_max_months": 24,
        "amount_min": "5000.00",
        "amount_max": "50000.00",
        "withdrawal_min": "2000.00",
        "withdrawal_max": "20000.00",
        "purchase_min": "5000.00",
        "purchase_max": "50000.00",
        "sip_amount_min": "5000.00",
        "sip_amount_max": "20000.00",
        "initial_contribution_min": "50000.00",
        "initial_contribution_max": "100000.00",
        "redeem_fraction_percent_min": 10,
        "redeem_fraction_percent_max": 80,
        "correction_rate_percent": 25,
        "correction_type_weights": {"REPLACE": 60, "VOID": 20, "REVERSE_AND_REPLACE": 20},
        "backdating_delay_days_min": 1,
        "backdating_delay_days_max": 30,
        "correction_eligible_types": ["CONTRIBUTION", "PURCHASE", "REDEMPTION"],
        "synthetic_operator_count": 5,
        "transaction_recorded_hour_utc": 18,
        "transaction_recorded_minute_window": 120,
        "correction_recorded_hour_utc": 11,
        "correction_recorded_minute_window": 240,
        "scheme_pool_min_observations": 750,
        "scheme_pool_min_first_nav_date": "2014-01-01",
        "scheme_pool_max_paths": 30,
        "rounding": {"amount_dp": 2, "units_dp": 3, "units_mode": "ROUND_DOWN", "amount_mode": "ROUND_HALF_UP"},
    }
    document.update(overrides)
    return GeneratorConfig.from_mapping(document)


def test_canonical_hash_is_stable(tmp_path) -> None:
    payload = {"b": Decimal("10.500"), "a": date(2024, 1, 1)}
    first = canonical_hash(payload)
    second = canonical_hash({"a": date(2024, 1, 1), "b": Decimal("10.500")})
    assert first == second
    assert len(first) == 64
    assert canonical_bytes(payload).decode("utf-8") == '{"a":"2024-01-01","b":"10.500"}'


def test_same_seed_produces_identical_records(tmp_path) -> None:
    config = _config(tmp_path)
    nav_index = _nav_index()
    first = SyntheticGenerator(config, nav_index).generate()
    second = SyntheticGenerator(config, nav_index).generate()
    assert [t.to_canonical() for t in first.transactions] == [t.to_canonical() for t in second.transactions]
    assert [a.to_canonical() for a in first.accounts] == [a.to_canonical() for a in second.accounts]
    assert first.manifest["hashes"] == second.manifest["hashes"]
    assert first.manifest["hashes"]["dataset"] == second.manifest["hashes"]["dataset"]


def test_different_seed_changes_hash(tmp_path) -> None:
    base = _config(tmp_path, seed=42)
    alt = _config(tmp_path, seed=43)
    nav_index = _nav_index()
    first = SyntheticGenerator(base, nav_index).generate()
    second = SyntheticGenerator(alt, nav_index).generate()
    assert first.manifest["hashes"]["dataset"] != second.manifest["hashes"]["dataset"]
    assert first.manifest["config_hash"] != second.manifest["config_hash"]


def test_all_transactions_synthetic_and_approved_types(tmp_path) -> None:
    dataset = SyntheticGenerator(_config(tmp_path), _nav_index()).generate()
    assert dataset.transactions
    approved = {"CONTRIBUTION", "WITHDRAWAL", "PURCHASE", "REDEMPTION", "SIP_INSTALMENT", "SWITCH"}
    for txn in dataset.transactions:
        assert txn.txn_type in approved
        assert txn.data_class == "synthetic_accounts_real_nav"
        assert txn.synthetic_label == "synthetic_accounts_real_nav"
        assert txn.amount_instructed is None or txn.amount_instructed > 0
        assert txn.units_instructed is None or txn.units_instructed > 0


def test_nav_aligned_effective_dates(tmp_path) -> None:
    dataset = SyntheticGenerator(_config(tmp_path), _nav_index()).generate()
    nav_index = _nav_index()
    for txn in dataset.transactions:
        if txn.txn_type in ("PURCHASE", "REDEMPTION", "SIP_INSTALMENT"):
            assert txn.allotment_date == txn.effective_date
            assert nav_index.price(txn.scheme_code or "", txn.effective_date) is not None
        if txn.txn_type == "SWITCH":
            assert txn.allotment_date == txn.effective_date
            assert nav_index.price(txn.source_scheme_code or "", txn.effective_date) is not None
            assert nav_index.price(txn.target_scheme_code or "", txn.effective_date) is not None


def test_posting_sequences_are_positive(tmp_path) -> None:
    dataset = SyntheticGenerator(_config(tmp_path), _nav_index()).generate()
    for txn in dataset.transactions:
        assert txn.posting_sequence > 0
        assert txn.posting_sequence % 10 == 0


def test_correction_intents_are_not_applied_and_are_later(tmp_path) -> None:
    dataset = SyntheticGenerator(_config(tmp_path), _nav_index()).generate()
    txn_by_id = {txn.txn_group_id: txn for txn in dataset.transactions}
    assert dataset.correction_intents
    for intent in dataset.correction_intents:
        original = txn_by_id[intent.txn_group_id]
        assert intent.recorded_at > original.recorded_at
        assert intent.correction_type in {"REPLACE", "VOID", "REVERSE_AND_REPLACE"}
        assert intent.data_class == "synthetic_accounts_real_nav"


def test_manifest_counts_and_hashes_present(tmp_path) -> None:
    dataset = SyntheticGenerator(_config(tmp_path), _nav_index()).generate()
    manifest = dataset.manifest
    assert manifest["counts"]["investors"] == 3
    assert manifest["counts"]["accounts"] == 4
    assert manifest["counts"]["transactions"] == len(dataset.transactions)
    assert manifest["counts"]["correction_intents"] == len(dataset.correction_intents)
    assert len(manifest["hashes"]["dataset"]) == 64
    assert manifest["scheme_pool"] == ["119436", "119528", "119620"]


def test_no_binary_float_in_amounts(tmp_path) -> None:
    dataset = SyntheticGenerator(_config(tmp_path), _nav_index()).generate()
    for txn in dataset.transactions:
        assert not isinstance(txn.amount_instructed, float)
        assert not isinstance(txn.units_instructed, float)
        assert not isinstance(txn.generator_estimated_units, float)
