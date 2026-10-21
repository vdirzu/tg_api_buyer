import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.database.models import (
    AcceptedKey,
    AuditLog,
    PendingAcceptance,
    Transaction,
    VerificationAttempt,
)
from app.services.errors import BusinessError
from app.services.pricing import payment, positive


def error(code):
    return pytest.raises(BusinessError, match=f"^{code}$")


async def accept(market, number, user=10):
    return await market.accept(user, "a", f"key-{number}")


async def withdrawal(market, card, amount="10", user=10, token=None):
    return await market.withdraw(user, amount, "USD", "card", "Visa", card, token or str(uuid4()))


async def test_preferences_persist_without_changing_value(market):
    await accept(market, 1)
    await market.preferences(10, language="ru", currency="RUB")
    user = await market.user(10)
    assert (user.language, user.currency, user.available_usd) == ("ru", "RUB", Decimal("30"))
    _, shown = await market.shown_balance(user)
    assert shown == Decimal("3000")
    await market.preferences(10, currency="USD")
    assert (await market.user(10)).available_usd == Decimal("30")


async def test_product_crud_and_authorization(market):
    with error("unauthorized"):
        await market.save_product(10, {"id": "a", "rate": "0.5"})
    await market.save_product(
        1, {"id": "a", "rate": "0.5", "name_en": "Changed", "display_order": 2, "image": "file_id"}
    )
    product = await market.product("a")
    assert product.rate == Decimal("0.5") and product.image == "file_id"
    await market.save_product(1, {"id": "a", "active": False})
    assert await market.products() == []
    with error("product_unavailable"):
        await accept(market, 1)
    await market.save_product(1, {"id": "a", "active": True})
    assert len(await market.products()) == 1


async def test_csv_lookup_rejections_and_failed_count(market):
    for key, code in [
        ("missing", "key_not_found"),
        ("key-29", "wrong_provider"),
        ("key-30", "invalid_key"),
    ]:
        with error(code):
            await market.accept(10, "a", key)
    assert (await market.user(10)).accepted_count == 0
    first = await accept(market, 1)
    assert first.discount == 0
    async with market.sessions() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(VerificationAttempt)
                .where(VerificationAttempt.outcome != "credited")
            )
            == 3
        )


async def test_second_key_only_discount_even_csv_true_on_third(market):
    results = [await accept(market, i) for i in range(1, 5)]
    assert [r.payment_usd for r in results] == list(map(Decimal, ["30", "24", "30", "30"]))
    assert [r.test_region_restricted for r in results] == [False, True, False, False]
    assert results[2].csv_region_restricted is True
    user = await market.user(10)
    assert user.available_usd == user.earned_usd == Decimal("114")
    assert user.accepted_count == 4
    async with market.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(Transaction)) == 4


async def test_duplicate_key_global_and_retry(market):
    await accept(market, 1)
    with error("duplicate_key"):
        await accept(market, 1)
    await market.user(11)
    await market.preferences(11, language="ru", currency="RUB")
    with error("duplicate_key"):
        await accept(market, 1, 11)
    assert (await market.user(10)).available_usd == Decimal("30")
    assert (await market.user(11)).available_usd == 0


async def test_concurrent_same_fingerprint_across_users(market):
    await market.user(11)
    await market.preferences(11, language="en", currency="USD")
    results = await asyncio.gather(accept(market, 1), accept(market, 1, 11), return_exceptions=True)
    assert sum(isinstance(r, AcceptedKey) for r in results) == 1
    assert sum(isinstance(r, BusinessError) and r.code == "duplicate_key" for r in results) == 1
    assert (await market.user(10)).available_usd + (await market.user(11)).available_usd == Decimal(
        "30"
    )


async def test_concurrent_distinct_keys_same_user_second_rule(market):
    results = await asyncio.gather(*(accept(market, i) for i in range(1, 6)))
    assert sum(r.discount == Decimal("0.20") for r in results) == 1
    assert (await market.user(10)).available_usd == Decimal("144")


async def test_rub_snapshot_and_pending_conversion(market):
    await market.preferences(10, currency="RUB")
    market.rates.failed = True
    with error("rate_unavailable"):
        await accept(market, 1)
    user = await market.user(10)
    assert user.accepted_count == 0 and user.available_usd == 0
    async with market.sessions() as s:
        pending = await s.get(PendingAcceptance, 10)
        assert len(pending.fingerprint) == 64 and pending.purchase_rate == Decimal("0.30")
    await market.save_product(1, {"id": "a", "rate": "0.7"})
    market.rates.failed = False
    result = await market.retry_pending(10)
    assert result.exchange_rate == 100 and result.credited_amount == 3000
    assert result.payment_usd == 30 and result.rate_source == "test fixture"
    assert result.rate_observed_at is not None
    assert (await market.user(10)).available_usd == 30
    with error("not_found"):
        await market.retry_pending(10)


async def test_atomic_rollback_if_ledger_insert_fails(market):
    async with market.sessions() as s, s.begin():
        await s.execute(
            text(
                "CREATE FUNCTION fail_ledger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test ledger failure'; END; $$"
            )
        )
        await s.execute(
            text(
                "CREATE TRIGGER reject_ledger BEFORE INSERT ON transactions FOR EACH ROW EXECUTE FUNCTION fail_ledger()"
            )
        )
    with pytest.raises(DBAPIError):
        await accept(market, 1)
    assert (await market.user(10)).available_usd == 0
    assert (await market.user(10)).accepted_count == 0
    async with market.sessions() as s, s.begin():
        assert await s.scalar(select(func.count()).select_from(AcceptedKey)) == 0
        await s.execute(text("DROP TRIGGER reject_ledger ON transactions"))
    assert (await accept(market, 1)).payment_usd == 30


@pytest.mark.parametrize(
    "amount,code",
    [
        ("-1", "invalid_amount"),
        ("0", "invalid_amount"),
        ("NaN", "invalid_amount"),
        ("Infinity", "invalid_amount"),
        ("0.001", "invalid_amount"),
        ("0.50", "below_minimum"),
        ("31", "insufficient_funds"),
    ],
)
async def test_withdrawal_validation(market, card, amount, code):
    await accept(market, 1)
    with error(code):
        await withdrawal(market, card, amount)
    assert (await market.user(10)).available_usd == 30


async def test_reserve_release_and_audit(market, card):
    await accept(market, 1)
    result = await withdrawal(market, card)
    assert (await market.user(10)).available_usd == 20
    assert (await market.user(10)).reserved_usd == 10
    assert card not in result.encrypted_details
    with error("unauthorized"):
        await market.withdrawal_details(10, result.id)
    row, details = await market.withdrawal_details(1, result.id)
    assert details == card
    with error("reason_required"):
        await market.transition(1, row.id, "rejected")
    await market.transition(1, row.id, "rejected", "Test rejection")
    await market.transition(1, row.id, "rejected", "Repeated")
    user = await market.user(10)
    assert user.available_usd == 30 and user.reserved_usd == 0
    async with market.sessions() as s:
        audits = list(
            await s.scalars(select(AuditLog).where(AuditLog.event == "withdraw.transition"))
        )
        assert len(audits) == 1 and audits[0].actor_id == 1
        assert audits[0].details["reason"] == "Test rejection"


async def test_paid_request_cannot_be_refunded_or_paid_twice(market, card):
    await accept(market, 1)
    row = await withdrawal(market, card, "20")
    await market.transition(1, row.id, "processing")
    await asyncio.gather(*(market.transition(1, row.id, "paid") for _ in range(4)))
    user = await market.user(10)
    assert (user.available_usd, user.reserved_usd, user.withdrawn_usd) == (10, 0, 20)
    with error("invalid_transition"):
        await market.transition(1, row.id, "rejected", "No double refund")
    async with market.sessions() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.kind == "withdraw_paid")
            )
            == 1
        )


async def test_concurrent_withdrawals_cannot_overspend(market, card):
    await accept(market, 1)
    results = await asyncio.gather(
        withdrawal(market, card, "20"), withdrawal(market, card, "20"), return_exceptions=True
    )
    assert (
        sum(isinstance(r, BusinessError) and r.code == "insufficient_funds" for r in results) == 1
    )
    assert (await market.user(10)).reserved_usd == 20


async def test_withdrawal_retry_token_is_idempotent(market, card):
    await accept(market, 1)
    token = str(uuid4())
    rows = await asyncio.gather(*(withdrawal(market, card, token=token) for _ in range(4)))
    assert len({r.id for r in rows}) == 1
    assert (await market.user(10)).reserved_usd == 10


async def test_rub_withdrawal_snapshots_and_currency_race(market, card):
    await accept(market, 1)
    await market.preferences(10, currency="RUB")
    with error("currency_changed"):
        await withdrawal(market, card)
    row = await market.withdraw(10, "1000", "RUB", "card", "Visa", card, str(uuid4()))
    assert row.amount_usd == 10 and row.exchange_rate == 100
    await market.preferences(10, currency="USD")
    await market.transition(1, row.id, "cancelled", "Return")
    assert (await market.user(10)).available_usd == 30


async def test_admin_management_final_admin_and_bootstrap(market):
    with error("last_admin"):
        await market.change_admin(1, 1, False)
    with error("unauthorized"):
        await market.change_admin(10, 11, True)
    await market.change_admin(1, 2, True)
    await market.change_admin(2, 1, False)
    await market.bootstrap([1])
    assert not await market.is_admin(1)
    with error("unauthorized"):
        await market.dashboard(1)
    with error("last_admin"):
        await market.change_admin(2, 2, False)


async def test_concurrent_admin_removals_preserve_last(market):
    await market.change_admin(1, 2, True)
    results = await asyncio.gather(
        market.change_admin(1, 1, False), market.change_admin(2, 2, False), return_exceptions=True
    )
    assert sum(isinstance(r, BusinessError) for r in results) == 1
    assert len(await market.admins(1 if await market.is_admin(1) else 2)) == 1


async def test_content_images_and_config_validation(market):
    await market.set_config(1, "welcome.ru", "Привет!")
    await market.set_config(1, "image.main", "telegram_file_id")
    await market.set_config(1, "minimum.RUB", "500.00")
    await market.set_config(1, "terms_url.en", "https://example.com/terms")
    settings = await market.settings()
    assert settings["welcome.ru"] == "Привет!" and settings["image.main"] == "telegram_file_id"
    for key, value in [
        ("terms_url.ru", "javascript:alert(1)"),
        ("minimum.USD", "NaN"),
        ("image.invalid", "x"),
        ("exchange.ttl", 0),
        ("message.progress_lookup.en", "{unsafe}"),
    ]:
        with pytest.raises(BusinessError):
            await market.set_config(1, key, value)
    with error("unauthorized"):
        await market.set_config(10, "welcome.en", "Malicious edit")


async def test_crypto_management_and_address_validation(market):
    await accept(market, 1)
    for option in await market.crypto_options():
        assert option.asset in {"USDT", "USDC", "TON"}
    await market.save_crypto(
        1,
        {
            "id": "extra",
            "asset": "TEST",
            "network": "Ethereum",
            "address_kind": "evm",
            "active": True,
        },
    )
    with error("invalid_destination"):
        await market.withdraw(10, "2", "USD", "crypto", "extra", "not-an-address", str(uuid4()))
    row = await market.withdraw(10, "2", "USD", "crypto", "extra", "0x" + "1" * 40, str(uuid4()))
    assert row.destination_label == "TEST / Ethereum"
    await market.save_crypto(1, {"id": "extra", "active": False})
    with error("invalid_destination"):
        await market.withdraw(10, "2", "USD", "crypto", "extra", "0x" + "1" * 40, str(uuid4()))


async def test_dashboard_and_ownership_pagination(market, card):
    for i in range(1, 8):
        await accept(market, i)
    await withdrawal(market, card)
    data = await market.dashboard(1)
    assert data["users"] == 1 and data["accepted"] == 7
    assert Decimal(data["credited_usd"]) == 204 and data["pending_count"] == 1
    assert len(await market.history(10, "keys", 0)) == 6
    assert len(await market.history(10, "keys", 1)) == 2
    assert await market.history(11, "keys", 0) == []
    with error("unauthorized"):
        await market.inspect_user(10, 10)


async def test_submission_throttle(market):
    market.submission_interval = 60
    with error("key_not_found"):
        await market.accept(10, "a", "missing")
    with error("rate_limited"):
        await accept(market, 1)
    assert (await market.user(10)).accepted_count == 0


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "1.001", "abc"])
def test_amount_input_is_finite_positive_cents(value):
    with error("invalid_amount"):
        positive(value, cents=True)


def test_decimal_calculation():
    assert payment(Decimal("100"), Decimal("0.30"), 1) == (Decimal("24.00"), Decimal("0.20"))
    assert payment(Decimal("0.1"), Decimal("0.3"), 0)[0] == Decimal("0.03")


async def test_committed_history_is_immutable_in_migrated_schema(market):
    await accept(market, 1)
    for table in ("audit_log", "accepted_keys", "transactions"):
        async with market.sessions() as s:
            with pytest.raises(DBAPIError, match="append-only"):
                await s.execute(text(f"DELETE FROM {table}"))
            await s.rollback()
            assert await s.scalar(text(f"SELECT count(*) FROM {table}")) >= 1


async def test_withdraw_reservation_rolls_back_on_ledger_failure(market, card):
    await accept(market, 1)
    async with market.sessions() as s, s.begin():
        await s.execute(
            text(
                "CREATE FUNCTION fail_withdraw_ledger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test'; END; $$"
            )
        )
        await s.execute(
            text(
                "CREATE TRIGGER reject_withdraw_ledger BEFORE INSERT ON transactions FOR EACH ROW EXECUTE FUNCTION fail_withdraw_ledger()"
            )
        )
    with pytest.raises(DBAPIError):
        await withdrawal(market, card)
    user = await market.user(10)
    assert user.available_usd == 30 and user.reserved_usd == 0
    async with market.sessions() as s:
        from app.database.models import Withdrawal

        assert await s.scalar(select(func.count()).select_from(Withdrawal)) == 0
