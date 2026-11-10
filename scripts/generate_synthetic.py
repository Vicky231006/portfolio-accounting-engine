"""Generate deterministic synthetic logical records (M2 CLI)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from bitemporal_ledger.generator.config import GeneratorConfig
from bitemporal_ledger.generator.generator import SyntheticGenerator
from bitemporal_ledger.generator.nav_index import (
    eligible_scheme_codes_from_db,
    load_nav_index_from_db,
)


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return dsn


def _pretty_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _decimal_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"Not serialisable: {type(value)!r}")


def generate_and_write(config_path: str, output_dir: str, database_url: str) -> dict:
    config = GeneratorConfig.from_yaml(config_path)
    scheme_codes = eligible_scheme_codes_from_db(
        database_url,
        config.nav_snapshot_id,
        config.scheme_pool_min_observations,
        config.scheme_pool_min_first_nav_date,
        config.scheme_pool_max_paths,
    )
    if not scheme_codes:
        raise RuntimeError("No eligible schemes in the NAV snapshot for the configured pool rules")
    nav_index = load_nav_index_from_db(database_url, config.nav_snapshot_id, scheme_codes)
    dataset = SyntheticGenerator(config, nav_index).generate()

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    investors = [_primitive(inv.to_canonical()) for inv in dataset.investors]
    accounts = [_primitive(acc.to_canonical()) for acc in dataset.accounts]
    transactions = [_primitive(txn.to_canonical()) for txn in dataset.transactions]
    intents = [_primitive(intent.to_canonical()) for intent in dataset.correction_intents]
    (out / "investors.json").write_bytes(_pretty_bytes(investors))
    (out / "accounts.json").write_bytes(_pretty_bytes(accounts))
    (out / "transactions.json").write_bytes(_pretty_bytes(transactions))
    (out / "correction_intents.json").write_bytes(_pretty_bytes(intents))
    (out / "manifest.json").write_bytes(_pretty_bytes(dataset.manifest))
    return dataset.manifest


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")  # type: ignore[union-attr]
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic logical records (M2)")
    parser.add_argument("--config", default="config/generator.yaml")
    parser.add_argument("--output-dir", default="output/synthetic/run1")
    args = parser.parse_args(argv)
    manifest = generate_and_write(args.config, args.output_dir, _dsn())
    print(f"investors={manifest['counts']['investors']} accounts={manifest['counts']['accounts']}")
    print(f"transactions={manifest['counts']['transactions']} correction_intents={manifest['counts']['correction_intents']}")
    print(f"transaction_counts_by_type={manifest['transaction_counts_by_type']}")
    print(f"dataset_hash={manifest['hashes']['dataset']}")
    print(f"config_hash={manifest['config_hash']}")
    print(f"schema_pool={manifest['scheme_pool'][:3]} ... ({len(manifest['scheme_pool'])} schemes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
