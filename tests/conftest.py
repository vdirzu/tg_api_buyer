import csv
import os
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.csv_verification import CSVVerifier, fingerprint
from app.services.exchange_rates import ExchangeRates, Rate
from app.services.marketplace import Marketplace

TEST_URL = os.environ.get("TEST_DATABASE_URL")
SECRET = "synthetic-test-hmac-secret-for-unit-tests-only"


class FixedRates(ExchangeRates):
    def __init__(self):
        super().__init__("https://open.er-api.com/v6/latest/USD")
        self.failed = False

    async def get(self, currency, **kwargs):
        from datetime import UTC, datetime
        from app.services.errors import BusinessError

        if currency == "RUB" and self.failed:
            raise BusinessError("rate_unavailable")
        return Rate(
            Decimal("100") if currency == "RUB" else Decimal(1), "test fixture", datetime.now(UTC)
        )


@pytest_asyncio.fixture
async def market(tmp_path):
    if not TEST_URL:
        pytest.fail(
            "Set TEST_DATABASE_URL to an isolated PostgreSQL instance; integration tests are required."
        )
    schema = "test_" + uuid4().hex
    control = create_async_engine(TEST_URL)
    async with control.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        TEST_URL, hide_parameters=True, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as conn:

        def migrate(connection):
            from alembic import command
            from alembic.config import Config

            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        await conn.run_sync(migrate)
    path = tmp_path / "keys.csv"
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["key_fingerprint", "provider_id", "balance_usd", "region_restricted", "test_status"]
        )
        for i in range(1, 31):
            writer.writerow(
                [
                    fingerprint(f"key-{i}", SECRET),
                    "b" if i == 29 else "a",
                    "100.00",
                    "true" if i == 3 else "false",
                    "invalid" if i == 30 else "valid",
                ]
            )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    instance = Marketplace(
        sessions, CSVVerifier(path, SECRET), FixedRates(), Fernet.generate_key().decode(), 0
    )
    await instance.bootstrap([1])
    await instance.save_product(
        1, {"id": "a", "name_ru": "Провайдер A", "name_en": "Provider A", "rate": "0.30"}
    )
    await instance.user(10)
    await instance.preferences(10, language="en", currency="USD")
    yield instance
    await engine.dispose()
    async with control.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await control.dispose()


@pytest.fixture
def card():
    return "4111111111111111"  # Public synthetic Visa test number.
