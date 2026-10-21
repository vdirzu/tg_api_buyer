"""Local operator tools. Never send real provider keys to this CSV test bot."""

import argparse
import asyncio
import csv
import os
import tempfile
from pathlib import Path

from sqlalchemy import text

from app.runtime import run_async
from app.config import Settings
from app.main import build_market
from app.services.csv_verification import fingerprint


async def check(settings):
    engine, market = build_market(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1 FROM users LIMIT 1"))
        records = await asyncio.to_thread(market.verifier._read)
        print(f"Database schema reachable; CSV valid: {len(records)} records.")
    finally:
        await engine.dispose()


async def seed(settings):
    engine, market = build_market(settings)
    try:
        await market.bootstrap(settings.admin_ids)
        print("Administrators and withdrawal options initialized. No products or money added.")
    finally:
        await engine.dispose()


def sample(settings, output, force=False):
    path = Path(output or settings.csv_path)
    if path.exists() and not force:
        raise SystemExit("Output exists; use --force only to replace your own test file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".keys-", suffix=".csv")
    try:
        with os.fdopen(handle, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                [
                    "key_fingerprint",
                    "provider_id",
                    "balance_usd",
                    "region_restricted",
                    "test_status",
                ]
            )
            for number in range(1, 11):
                writer.writerow(
                    [
                        fingerprint(
                            f"synthetic-key-{number}", settings.key_hmac_secret.get_secret_value()
                        ),
                        "provider_a" if number < 9 else "provider_b",
                        "100.00",
                        "true" if number == 3 else "false",
                        "invalid" if number == 10 else "valid",
                    ]
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(
        "Synthetic CSV written atomically. Example inputs: synthetic-key-1 through synthetic-key-10."
    )


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("seed")
    generate = sub.add_parser("sample-csv")
    generate.add_argument("--output")
    generate.add_argument("--force", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "sample-csv":
        sample(settings, args.output, args.force)
    else:
        run_async(check(settings) if args.command == "check" else seed(settings))


if __name__ == "__main__":
    main()
