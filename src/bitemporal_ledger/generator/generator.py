"""Deterministic synthetic generator (M2, D-034 to D-039).

The generator is a pure logical-record function: there is no ledger, no
correction engine, no valuation and no performance calculation here. It
emits instruction-level transaction intents, investor/account master data
and unrealised correction intents, with a feasibility-only cash/holdings
simulation that guarantees the generated dataset is economically valid
under the approved rules (D-027, D-037).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from bitemporal_ledger.generator.canonical import canonical_hash, dataset_hash
from bitemporal_ledger.generator.config import GeneratorConfig
from bitemporal_ledger.generator.models import (
    Account,
    CorrectionIntent,
    GeneratedDataset,
    Investor,
    Transaction,
)
from bitemporal_ledger.generator.nav_index import NavIndex

_DATA_CLASS = "synthetic_accounts_real_nav"
_CENT = Decimal("0.01")
_UNIT_DP = Decimal("0.001")
_UNITS_Q = Decimal("0.001")


@dataclass
class _AccountState:
    account: Account
    cash: Decimal = Decimal("0.00")
    holdings: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class _TimelineEvent:
    effective_date: date
    order: int
    kind: str  # SIP | DISC | FUNDING
    payload: dict


class SyntheticGenerator:
    """Generate one deterministic dataset for (config, seed, NAV index)."""

    def __init__(self, config: GeneratorConfig, nav_index: NavIndex, rng: random.Random | None = None) -> None:
        if not nav_index.scheme_codes:
            raise ValueError("NAV index must contain at least one eligible scheme")
        self.config = config
        self.nav_index = nav_index
        self.rng = rng if rng is not None else random.Random(config.seed)

    # ------------------------------------------------------------------ entry

    def generate(self) -> GeneratedDataset:
        investors = self._generate_investors()
        accounts = self._generate_accounts(investors)
        transactions: list[Transaction] = []
        txn_counter = 0
        for account in sorted(accounts, key=lambda acc: acc.account_id):
            account_txns = self._generate_account_transactions(account)
            transactions.extend(account_txns)
            txn_counter += len(account_txns)
        transactions = self._assign_posting_sequences_and_recorded_at(transactions)
        transactions = sorted(
            transactions,
            key=lambda txn: (txn.account_id, txn.effective_date, txn.posting_sequence, txn.txn_group_id),
        )
        intents = self._generate_correction_intents(transactions)
        manifest = self._build_manifest(investors, accounts, transactions, intents)
        return GeneratedDataset(
            investors=investors,
            accounts=accounts,
            transactions=transactions,
            correction_intents=intents,
            manifest=manifest,
        )

    # ------------------------------------------------------------------ master

    def _generate_investors(self) -> list[Investor]:
        cfg = self.config
        return [
            Investor(
                investor_id=investor_id,
                synthetic_ref=f"SYN_INV-{investor_id:04d}",
                display_name=f"Synthetic Investor {investor_id:02d}",
                data_class=_DATA_CLASS,
                synthetic_label=cfg.synthetic_label,
            )
            for investor_id in range(1, cfg.investor_count + 1)
        ]

    def _generate_accounts(self, investors: list[Investor]) -> list[Account]:
        cfg = self.config
        accounts: list[Account] = []
        for idx in range(1, cfg.account_count + 1):
            investor_id = investors[(idx - 1) % len(investors)].investor_id
            is_active = self.rng.randint(1, 100) <= cfg.active_percent
            status = "ACTIVE" if is_active else "CLOSED"
            opened = self._random_date(cfg.account_opening_start, cfg.account_opening_end)
            closed: date | None = None
            if status == "CLOSED":
                closed = opened + timedelta(days=self.rng.randint(180, 1500))
                if closed > cfg.transaction_end:
                    closed = cfg.transaction_end - timedelta(days=self.rng.randint(1, 30))
            accounts.append(
                Account(
                    account_id=idx,
                    investor_id=investor_id,
                    synthetic_ref=f"SYN_ACC-{idx:04d}",
                    display_name=f"Synthetic Account {idx:02d}",
                    account_status=status,
                    currency="INR",
                    opened_date=opened,
                    closed_date=closed,
                    data_class=_DATA_CLASS,
                    synthetic_label=cfg.synthetic_label,
                )
            )
        return accounts

    # ------------------------------------------------------------------ plumbing

    def _random_date(self, start: date, end: date) -> date:
        if end < start:
            raise ValueError("end must not be before start")
        span = (end - start).days
        return start + timedelta(days=self.rng.randint(0, span))

    def _random_amount(self, minimum: Decimal, maximum: Decimal) -> Decimal:
        min_paise = int(minimum * 100)
        max_paise = int(maximum * 100)
        paise = self.rng.randint(min_paise, max_paise)
        return Decimal(paise) * _CENT

    def _pick_scheme(self) -> str:
        codes = self.nav_index.scheme_codes
        return codes[self.rng.randint(0, len(codes) - 1)]

    def _weighted_type(self, weights: dict[str, int]) -> str:
        total = sum(weights.values())
        roll = self.rng.randint(1, total)
        running = 0
        for key in sorted(weights):
            running += weights[key]
            if roll <= running:
                return key
        return sorted(weights)[-1]

    @staticmethod
    def _quant_amount(value: Decimal) -> Decimal:
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _quant_units(value: Decimal) -> Decimal:
        return value.quantize(_UNITS_Q, rounding=ROUND_DOWN)

    def _nav_price(self, scheme: str, nav_date: date) -> Decimal | None:
        return self.nav_index.price(scheme, nav_date)

    # ------------------------------------------------------------------ per-account

    def _generate_account_transactions(self, account: Account) -> list[Transaction]:
        cfg = self.config
        active_end = account.closed_date or cfg.transaction_end
        start = account.opened_date
        state = _AccountState(account=account)
        events: list[_TimelineEvent] = []
        order = 0

        funding_date = start + timedelta(days=self.rng.randint(0, 30))
        if funding_date > active_end:
            funding_date = active_end
        events.append(_TimelineEvent(funding_date, order, "FUNDING", {}))
        order += 1

        n_sip = self.rng.randint(cfg.sip_schedules_per_account_min, cfg.sip_schedules_per_account_max)
        for _ in range(n_sip):
            scheme = self._pick_scheme()
            sip_amount = self._random_amount(cfg.sip_amount_min, cfg.sip_amount_max)
            sip_day = self.rng.randint(cfg.sip_day_of_month_min, cfg.sip_day_of_month_max)
            schedule_start = start + timedelta(days=self.rng.randint(0, 60))
            instalments = self._sip_dates(scheme, schedule_start, active_end, sip_day)
            for nominal in instalments:
                allotment = self.nav_index.first_nav_on_or_after(scheme, nominal, 5)
                if allotment is None or allotment > active_end:
                    continue
                events.append(
                    _TimelineEvent(
                        allotment,
                        order,
                        "SIP",
                        {"scheme": scheme, "amount": sip_amount, "nominal": nominal},
                    )
                )
                order += 1

        n_disc = self.rng.randint(cfg.discretionary_min_per_account, cfg.discretionary_max_per_account)
        for _ in range(n_disc):
            day = self._random_date(start, active_end)
            events.append(_TimelineEvent(day, order, "DISC", {}))
            order += 1

        events.sort(key=lambda event: (event.effective_date, event.order))
        emitted: list[Transaction] = []
        for event in events:
            txn = self._emit_event(account, state, event, len(emitted))
            if txn is not None:
                emitted.append(txn)
        return emitted

    def _sip_dates(self, scheme: str, start: date, end: date, sip_day: int) -> list[date]:
        result: list[date] = []
        year, month = start.year, start.month
        for _ in range(self.config.sip_schedule_max_months):
            nominal = self._month_day(year, month, sip_day)
            if nominal > end:
                break
            if nominal >= start:
                result.append(nominal)
            month += 1
            if month == 13:
                month, year = 1, year + 1
        return result

    @staticmethod
    def _month_day(year: int, month: int, day: int) -> date:
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = (next_month - timedelta(days=1)).day
        return date(year, month, min(day, last_day))

    def _emit_event(self, account: Account, state: _AccountState, event: _TimelineEvent, index_in_account: int) -> Transaction | None:
        if event.kind == "FUNDING":
            amount = self._random_amount(self.config.initial_contribution_min, self.config.initial_contribution_max)
            state.cash += amount
            return self._make_txn(
                account,
                "CONTRIBUTION",
                event.effective_date,
                amount=amount,
                scheme=None,
                estimated_units=None,
                estimated_proceeds=None,
            )
        if event.kind == "SIP":
            scheme = event.payload["scheme"]
            amount: Decimal = event.payload["amount"]
            price = self._nav_price(scheme, event.effective_date)
            if price is None:
                return None
            units = self._quant_units(amount / price)
            actual_cash = self._quant_amount(units * price)
            state.cash += amount
            state.cash -= actual_cash
            state.holdings[scheme] = state.holdings.get(scheme, Decimal("0")) + units
            return self._make_txn(
                account,
                "SIP_INSTALMENT",
                event.effective_date,
                amount=amount,
                scheme=scheme,
                estimated_units=units,
                estimated_proceeds=actual_cash,
            )
        return self._emit_discretionary(account, state, event, index_in_account)

    def _emit_discretionary(self, account: Account, state: _AccountState, event: _TimelineEvent, index_in_account: int) -> Transaction | None:
        cfg = self.config
        txn_type = self._weighted_type(cfg.transaction_weights)
        effective = event.effective_date

        if txn_type == "CONTRIBUTION":
            amount = self._random_amount(cfg.amount_min, cfg.amount_max)
            state.cash += amount
            return self._make_txn(account, "CONTRIBUTION", effective, amount=amount, scheme=None)

        if txn_type == "WITHDRAWAL":
            amount = self._random_amount(cfg.withdrawal_min, cfg.withdrawal_max)
            if amount > state.cash:
                capped = self._quant_amount(state.cash * Decimal("0.5"))
                if capped >= cfg.withdrawal_min:
                    amount = capped
                else:
                    fallback = self._random_amount(cfg.amount_min, cfg.amount_max)
                    state.cash += fallback
                    return self._make_txn(account, "CONTRIBUTION", effective, amount=fallback, scheme=None)
            state.cash -= amount
            return self._make_txn(account, "WITHDRAWAL", effective, amount=amount, scheme=None)

        if txn_type == "PURCHASE":
            scheme = self._pick_scheme()
            price = self._nav_price(scheme, effective)
            if price is None:
                amount = self._random_amount(cfg.amount_min, cfg.amount_max)
                state.cash += amount
                return self._make_txn(account, "CONTRIBUTION", effective, amount=amount, scheme=None)
            amount = self._random_amount(cfg.purchase_min, cfg.purchase_max)
            if amount > state.cash:
                amount = self._quant_amount(state.cash * Decimal("0.8"))
                if amount < cfg.purchase_min:
                    fallback = self._random_amount(cfg.amount_min, cfg.amount_max)
                    state.cash += fallback
                    return self._make_txn(account, "CONTRIBUTION", effective, amount=fallback, scheme=None)
            units = self._quant_units(amount / price)
            if units <= 0:
                fallback = self._random_amount(cfg.amount_min, cfg.amount_max)
                state.cash += fallback
                return self._make_txn(account, "CONTRIBUTION", effective, amount=fallback, scheme=None)
            actual_cash = self._quant_amount(units * price)
            state.cash -= actual_cash
            state.holdings[scheme] = state.holdings.get(scheme, Decimal("0")) + units
            return self._make_txn(
                account, "PURCHASE", effective, amount=amount, scheme=scheme,
                estimated_units=units, estimated_proceeds=actual_cash,
            )

        if txn_type == "REDEMPTION":
            scheme = self._pick_scheme()
            held = state.holdings.get(scheme, Decimal("0"))
            price = self._nav_price(scheme, effective)
            if held <= 0 or price is None:
                fallback_amount = self._random_amount(cfg.amount_min, cfg.amount_max)
                state.cash += fallback_amount
                return self._make_txn(account, "CONTRIBUTION", effective, amount=fallback_amount, scheme=None)
            fraction = Decimal(self.rng.randint(cfg.redeem_fraction_percent_min, cfg.redeem_fraction_percent_max)) / Decimal("100")
            units_req = self._quant_units(held * fraction)
            if units_req <= 0:
                return None
            proceeds = self._quant_amount(units_req * price)
            state.holdings[scheme] = held - units_req
            state.cash += proceeds
            return self._make_txn(
                account, "REDEMPTION", effective, units=units_req, scheme=scheme,
                estimated_units=units_req, estimated_proceeds=proceeds,
            )

        # SWITCH
        held_schemes = sorted([code for code, units in state.holdings.items() if units > 0])
        if not held_schemes:
            fallback_amount = self._random_amount(cfg.amount_min, cfg.amount_max)
            state.cash += fallback_amount
            return self._make_txn(account, "CONTRIBUTION", effective, amount=fallback_amount, scheme=None)
        source = held_schemes[self.rng.randint(0, len(held_schemes) - 1)]
        targets = [code for code in self.nav_index.scheme_codes if code != source]
        target = targets[self.rng.randint(0, len(targets) - 1)]
        source_price = self._nav_price(source, effective)
        target_price = self._nav_price(target, effective)
        if source_price is None or target_price is None:
            fallback_amount = self._random_amount(cfg.amount_min, cfg.amount_max)
            state.cash += fallback_amount
            return self._make_txn(account, "CONTRIBUTION", effective, amount=fallback_amount, scheme=None)
        fraction = Decimal(self.rng.randint(cfg.redeem_fraction_percent_min, cfg.redeem_fraction_percent_max)) / Decimal("100")
        units_out = self._quant_units(state.holdings[source] * fraction)
        if units_out <= 0:
            return None
        proceeds = self._quant_amount(units_out * source_price)
        units_target = self._quant_units(proceeds / target_price)
        if units_target <= 0:
            return None
        target_cost = self._quant_amount(units_target * target_price)
        residual = proceeds - target_cost
        state.holdings[source] -= units_out
        state.holdings[target] = state.holdings.get(target, Decimal("0")) + units_target
        state.cash += residual
        return self._make_txn(
            account, "SWITCH", effective, units=units_out, scheme=None,
            estimated_units=units_target, estimated_proceeds=proceeds,
            source_scheme=source, target_scheme=target,
        )

    def _make_txn(
        self,
        account: Account,
        txn_type: str,
        effective: date,
        *,
        amount: Decimal | None = None,
        units: Decimal | None = None,
        scheme: str | None = None,
        estimated_units: Decimal | None = None,
        estimated_proceeds: Decimal | None = None,
        source_scheme: str | None = None,
        target_scheme: str | None = None,
    ) -> Transaction:
        allotment = effective
        if txn_type in ("PURCHASE", "REDEMPTION", "SIP_INSTALMENT"):
            assert scheme is not None
            found = self.nav_index.first_nav_on_or_after(scheme, effective, 5)
            allotment = found if found is not None else effective
        instructional = {
            "txn_group_id": "PENDING",
            "account_id": account.account_id,
            "investor_id": account.investor_id,
            "txn_type": txn_type,
            "instruction_date": effective,
            "effective_date": effective,
            "allotment_date": allotment,
            "posting_sequence": 0,
            "scheme_code": scheme,
            "source_scheme_code": source_scheme,
            "target_scheme_code": target_scheme,
            "amount_instructed": amount,
            "units_instructed": units,
            "recorded_at": datetime(2000, 1, 1, tzinfo=timezone.utc),
            "generator_estimated_units": estimated_units,
            "generator_estimated_proceeds": estimated_proceeds,
            "data_class": _DATA_CLASS,
            "synthetic_label": self.config.synthetic_label,
        }
        return Transaction(**instructional)  # type: ignore[arg-type]

    # ------------------------------------------------------------------ sequencing

    def _assign_posting_sequences_and_recorded_at(self, transactions: list[Transaction]) -> list[Transaction]:
        cfg = self.config
        ordered = sorted(transactions, key=lambda txn: (txn.account_id, txn.effective_date, txn.instruction_date))
        counters: dict[tuple[int, date], int] = {}
        result: list[Transaction] = []
        global_index = 0
        for txn in ordered:
            key = (txn.account_id, txn.effective_date)
            counters[key] = counters.get(key, 0) + 1
            sequence = counters[key] * 10
            minute_offset = global_index % cfg.transaction_recorded_minute_window
            recorded = datetime.combine(
                txn.effective_date, time(cfg.transaction_recorded_hour_utc, 0, tzinfo=timezone.utc)
            ) + timedelta(minutes=minute_offset)
            result.append(
                Transaction(
                    txn_group_id=f"SYN_TXN-{global_index + 1:06d}",
                    account_id=txn.account_id,
                    investor_id=txn.investor_id,
                    txn_type=txn.txn_type,
                    instruction_date=txn.instruction_date,
                    effective_date=txn.effective_date,
                    allotment_date=txn.allotment_date,
                    posting_sequence=sequence,
                    scheme_code=txn.scheme_code,
                    source_scheme_code=txn.source_scheme_code,
                    target_scheme_code=txn.target_scheme_code,
                    amount_instructed=txn.amount_instructed,
                    units_instructed=txn.units_instructed,
                    recorded_at=recorded,
                    generator_estimated_units=txn.generator_estimated_units,
                    generator_estimated_proceeds=txn.generator_estimated_proceeds,
                    data_class=txn.data_class,
                    synthetic_label=txn.synthetic_label,
                )
            )
            global_index += 1
        return result

    # ------------------------------------------------------------------ corrections

    def _generate_correction_intents(self, transactions: list[Transaction]) -> list[CorrectionIntent]:
        cfg = self.config
        eligible = [txn for txn in transactions if txn.txn_type in cfg.correction_eligible_types]
        intents: list[CorrectionIntent] = []
        for txn in sorted(eligible, key=lambda item: item.txn_group_id):
            if self.rng.randint(1, 100) > cfg.correction_rate_percent:
                continue
            correction_type = self._weighted_type(cfg.correction_type_weights)
            delay = self.rng.randint(cfg.backdating_delay_days_min, cfg.backdating_delay_days_max)
            minute = len(intents) % cfg.correction_recorded_minute_window
            recorded = datetime.combine(
                txn.effective_date + timedelta(days=delay),
                time(cfg.correction_recorded_hour_utc, 0, tzinfo=timezone.utc),
            ) + timedelta(minutes=minute)
            actor = f"SYN_OP-{self.rng.randint(1, cfg.synthetic_operator_count):03d}"
            proposed_amount: Decimal | None = None
            proposed_units: Decimal | None = None
            proposed_scheme: str | None = None
            if correction_type == "REPLACE" and txn.amount_instructed is not None:
                factor = Decimal(self.rng.randint(105, 130)) / Decimal("100")
                proposed_amount = self._quant_amount(txn.amount_instructed * factor)
                reason = "SYN_AMOUNT_CORRECTION"
            elif correction_type == "REPLACE" and txn.units_instructed is not None:
                factor = Decimal(self.rng.randint(105, 130)) / Decimal("100")
                proposed_units = self._quant_units(txn.units_instructed * factor)
                reason = "SYN_UNITS_CORRECTION"
            elif correction_type == "REVERSE_AND_REPLACE":
                proposed_scheme = self._pick_scheme()
                if proposed_scheme == (txn.scheme_code or txn.target_scheme_code):
                    proposed_scheme = self._pick_scheme()
                reason = "SYN_SCHEME_CORRECTION"
            else:
                reason = "SYN_DUPLICATE_OR_ERROR"
            intents.append(
                CorrectionIntent(
                    correction_intent_id=f"SYN_CORR-{len(intents) + 1:05d}",
                    txn_group_id=txn.txn_group_id,
                    account_id=txn.account_id,
                    correction_type=correction_type,
                    reason_code=reason,
                    reason_note="Synthetic test correction intent; not a real error and not applied in M2.",
                    proposed_amount=proposed_amount,
                    proposed_units=proposed_units,
                    proposed_scheme_code=proposed_scheme,
                    proposed_effective_date=txn.effective_date if correction_type != "VOID" else None,
                    recorded_at=recorded,
                    actor_id=actor,
                    data_class=_DATA_CLASS,
                    synthetic_label=cfg.synthetic_label,
                )
            )
        return intents

    # ------------------------------------------------------------------ manifest

    def _build_manifest(self, investors: list[Investor], accounts: list[Account], transactions: list[Transaction], intents: list[CorrectionIntent]) -> dict:
        cfg = self.config
        investor_hashes = [canonical_hash(inv.to_canonical()) for inv in investors]
        account_hashes = [canonical_hash(acc.to_canonical()) for acc in accounts]
        txn_hashes = [canonical_hash(txn.to_canonical()) for txn in transactions]
        intent_hashes = [canonical_hash(intent.to_canonical()) for intent in intents]
        type_counts: dict[str, int] = {}
        for txn in transactions:
            type_counts[txn.txn_type] = type_counts.get(txn.txn_type, 0) + 1
        all_hashes = investor_hashes + account_hashes + txn_hashes + intent_hashes
        active = sum(1 for acc in accounts if acc.account_status == "ACTIVE")
        closed = sum(1 for acc in accounts if acc.account_status == "CLOSED")
        return {
            "generator_version": cfg.generator_version,
            "config_hash": cfg.config_hash(),
            "seed": cfg.seed,
            "nav_snapshot_id": cfg.nav_snapshot_id,
            "synthetic_label": cfg.synthetic_label,
            "disclaimer": cfg.disclaimer,
            "counts": {
                "investors": len(investors),
                "accounts": len(accounts),
                "active_accounts": active,
                "closed_accounts": closed,
                "transactions": len(transactions),
                "correction_intents": len(intents),
            },
            "transaction_counts_by_type": dict(sorted(type_counts.items())),
            "date_range": {
                "transaction_start": min((txn.effective_date for txn in transactions), default=None).isoformat() if transactions else None,
                "transaction_end": max((txn.effective_date for txn in transactions), default=None).isoformat() if transactions else None,
            },
            "hashes": {
                "investors": dataset_hash(investor_hashes),
                "accounts": dataset_hash(account_hashes),
                "transactions": dataset_hash(txn_hashes),
                "correction_intents": dataset_hash(intent_hashes),
                "dataset": dataset_hash(all_hashes),
            },
            "scheme_pool": self.nav_index.scheme_codes,
            "simulated_clock": {
                "transaction_recorded_rule": f"effective_date at {cfg.transaction_recorded_hour_utc:02d}:00 UTC + deterministic minute offset 0..{cfg.transaction_recorded_minute_window - 1}",
                "correction_recorded_rule": f"effective_date + 1..{cfg.backdating_delay_days_max} days at {cfg.correction_recorded_hour_utc:02d}:00 UTC + deterministic minute offset 0..{cfg.correction_recorded_minute_window - 1}",
                "wall_clock_used_in_logical_records": False,
            },
            "boundaries": [
                "No ledger tables written; correction intents are not applied (D-034, D-039).",
                "generator_estimated_units/proceeds are feasibility estimates only (D-037).",
                "Generated scheme transactions use NAV-available effective dates (D-036).",
            ],
        }
