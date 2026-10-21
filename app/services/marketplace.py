import re
from datetime import UTC, datetime, timedelta
from decimal import ROUND_UP
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.database.models import (
    AcceptedKey,
    Administrator,
    AuditLog,
    Configuration,
    CryptoOption,
    Product,
    Transaction,
    User,
    VerificationAttempt,
    Withdrawal,
    PendingAcceptance,
)
from app.services.csv_verification import CSVVerifier
from app.services.errors import BusinessError
from app.services.exchange_rates import ExchangeRates
from app.services.pricing import UNIT, display_amount, payment, positive

CRYPTO_DEFAULTS = [
    ("usdt_tron", "USDT", "TRON (TRC20)", "tron"),
    ("usdt_ethereum", "USDT", "Ethereum (ERC20)", "evm"),
    ("usdt_bsc", "USDT", "BNB Smart Chain (BEP20)", "evm"),
    ("usdc_ethereum", "USDC", "Ethereum", "evm"),
    ("usdc_solana", "USDC", "Solana", "solana"),
    ("ton", "TON", "The Open Network", "ton"),
]
SCREENS = {"welcome", "main", "catalog", "profile", "withdraw", "support", "about"}
CONTENT_KEYS = {
    "welcome",
    "main",
    "catalog",
    "profile",
    "withdraw",
    "support",
    "about",
    "terms_url",
    "privacy_url",
    "legal_fallback",
    "support_contact",
}


def audit(session, actor: int, event: str, entity: str, **details):
    session.add(AuditLog(actor_id=actor, event=event, entity=entity, details=details))


async def require_admin(session, actor: int):
    admin = await session.get(Administrator, actor)
    if not admin or not admin.active:
        raise BusinessError("unauthorized")


async def configuration(session, key: str, default: Any = None):
    item = await session.get(Configuration, key)
    return item.value if item else default


class Marketplace:
    def __init__(
        self,
        sessions,
        verifier: CSVVerifier,
        rates: ExchangeRates,
        encryption_key: str,
        submission_interval: int = 3,
    ):
        self.sessions, self.verifier, self.rates = sessions, verifier, rates
        self.cipher = Fernet(encryption_key.encode())
        self.submission_interval = submission_interval

    async def bootstrap(self, admin_ids: list[int]):
        async with self.sessions() as s, s.begin():
            await s.execute(text("SELECT pg_advisory_xact_lock(714202601)"))
            # Env IDs bootstrap only an empty admin table; removed admins never resurrect.
            if not await s.scalar(select(func.count()).select_from(Administrator)):
                if not admin_ids:
                    raise BusinessError("missing_admin")
                for actor in set(admin_ids):
                    if actor <= 0:
                        raise BusinessError("invalid_input")
                    s.add(Administrator(id=actor))
                    audit(s, actor, "admin.bootstrap", str(actor))
            for option_id, asset, network, kind in CRYPTO_DEFAULTS:
                if not await s.get(CryptoOption, option_id):
                    s.add(
                        CryptoOption(id=option_id, asset=asset, network=network, address_kind=kind)
                    )
            for key, value in {"minimum.USD": "1.00", "minimum.RUB": "100.00"}.items():
                if not await s.get(Configuration, key):
                    s.add(Configuration(key=key, value=value))

    async def user(self, user_id: int) -> User:
        from sqlalchemy.dialects.postgresql import insert

        async with self.sessions() as s, s.begin():
            await s.execute(insert(User).values(id=user_id).on_conflict_do_nothing())
            user = await s.get(User, user_id, with_for_update=True)
            user.last_active_at = datetime.now(UTC)
            return user

    async def preferences(self, user_id: int, *, language=None, currency=None):
        if language is not None and language not in {"ru", "en"}:
            raise BusinessError("invalid_input")
        if currency is not None and currency not in {"USD", "RUB"}:
            raise BusinessError("invalid_currency")
        async with self.sessions() as s, s.begin():
            user = await s.get(User, user_id, with_for_update=True)
            if language:
                user.language = language
            if currency:
                user.currency = currency

    async def settings(self) -> dict:
        async with self.sessions() as s:
            rows = (await s.scalars(select(Configuration))).all()
            return {row.key: row.value for row in rows}

    async def rate(self, session, currency: str):
        url = await configuration(session, "exchange.url", self.rates.url)
        ttl = int(await configuration(session, "exchange.ttl", self.rates.ttl))
        return await self.rates.get(currency, url=url, ttl=ttl)

    async def shown_balance(self, user: User):
        async with self.sessions() as s:
            rate = await self.rate(s, user.currency or "USD")
            return rate, display_amount(user.available_usd, rate.value)

    async def products(self, *, admin: int | None = None):
        async with self.sessions() as s:
            query = select(Product).order_by(Product.display_order, Product.id)
            if admin is not None:
                await require_admin(s, admin)
            else:
                query = query.where(Product.active.is_(True))
            return list(await s.scalars(query))

    async def product(self, product_id: str):
        async with self.sessions() as s:
            product = await s.get(Product, product_id)
            if not product or not product.active:
                raise BusinessError("product_unavailable")
            return product

    async def accept(
        self, user_id: int, product_id: str, key: str, *, _pending=None, progress=None
    ) -> AcceptedKey:
        fp, record, quote_rate = None, None, None
        try:
            # Persist the throttle even for rejected submissions.
            async with self.sessions() as s, s.begin():
                user = await s.get(User, user_id, with_for_update=True)
                if not user or user.status != "active" or not user.currency:
                    raise BusinessError("onboarding_required")
                now = datetime.now(UTC)
                if user.last_submission_at and now - user.last_submission_at < timedelta(
                    seconds=self.submission_interval
                ):
                    raise BusinessError("rate_limited")
                user.last_submission_at = now
            if _pending is None:
                fp, record = await self.verifier.lookup(key, product_id)
                if progress:
                    await progress("progress_region", record.region_restricted)
            else:
                from app.services.csv_verification import Record

                fp = _pending.fingerprint
                record = Record(
                    _pending.product_id,
                    _pending.balance_usd,
                    _pending.csv_region_restricted,
                    "valid",
                )
            async with self.sessions() as s, s.begin():
                user = await s.get(User, user_id, with_for_update=True)
                if not user or user.status != "active" or not user.currency:
                    raise BusinessError("onboarding_required")
                product = await s.get(Product, product_id, with_for_update=True)
                if not product or not product.active:
                    raise BusinessError("product_unavailable")
                if await s.scalar(select(AcceptedKey.id).where(AcceptedKey.fingerprint == fp)):
                    raise BusinessError("duplicate_key")
                if progress:
                    await progress("progress_balance", record.balance_usd)
                quote_rate = _pending.purchase_rate if _pending is not None else product.rate
                amount_usd, discount = payment(record.balance_usd, quote_rate, user.accepted_count)
                if progress:
                    await progress("progress_calculation", None)
                rate = await self.rate(s, user.currency)
                if progress:
                    await progress("progress_commit", None)
                if amount_usd <= 0:
                    raise BusinessError("invalid_amount")
                accepted = AcceptedKey(
                    user_id=user.id,
                    product_id=product.id,
                    fingerprint=fp,
                    balance_usd=record.balance_usd,
                    purchase_rate=quote_rate,
                    discount=discount,
                    csv_region_restricted=record.region_restricted,
                    test_region_restricted=(user.accepted_count == 1),
                    exchange_rate=rate.value,
                    rate_source=rate.source,
                    rate_observed_at=rate.observed_at,
                    payment_usd=amount_usd,
                    credited_amount=display_amount(amount_usd, rate.value),
                    currency=user.currency,
                )
                s.add(accepted)
                await s.flush()
                user.available_usd += amount_usd
                user.earned_usd += amount_usd
                user.accepted_count += 1
                pending = await s.get(PendingAcceptance, user_id)
                if pending and pending.fingerprint == fp:
                    await s.delete(pending)
                s.add(
                    Transaction(
                        user_id=user.id,
                        kind="key_credit",
                        amount_usd=amount_usd,
                        amount=accepted.credited_amount,
                        currency=user.currency,
                        status="credited",
                        accepted_key_id=accepted.id,
                    )
                )
                s.add(
                    VerificationAttempt(user_id=user.id, product_id=product_id, outcome="credited")
                )
                audit(s, user_id, "key.credit", str(accepted.id), amount_usd=str(amount_usd))
                return accepted
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
            if constraint != "accepted_keys_fingerprint_key":
                raise
            await self._failed(user_id, product_id, "duplicate_key")
            raise BusinessError("duplicate_key") from None
        except BusinessError as error:
            if error.code == "rate_unavailable" and fp and record and quote_rate:
                from sqlalchemy.dialects.postgresql import insert

                async with self.sessions() as s, s.begin():
                    values = dict(
                        user_id=user_id,
                        fingerprint=fp,
                        product_id=product_id,
                        balance_usd=record.balance_usd,
                        purchase_rate=quote_rate,
                        csv_region_restricted=record.region_restricted,
                    )
                    await s.execute(
                        insert(PendingAcceptance)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=[PendingAcceptance.user_id], set_=values
                        )
                    )
            await self._failed(user_id, product_id, error.code)
            raise

    async def retry_pending(self, user_id: int):
        async with self.sessions() as s:
            pending = await s.get(PendingAcceptance, user_id)
            if not pending:
                raise BusinessError("not_found")
        return await self.accept(user_id, pending.product_id, "", _pending=pending)

    async def _failed(self, user_id: int, product: str, outcome: str):
        async with self.sessions() as s, s.begin():
            if await s.get(User, user_id):
                s.add(VerificationAttempt(user_id=user_id, product_id=product, outcome=outcome))

    async def crypto_options(self):
        async with self.sessions() as s:
            return list(
                await s.scalars(
                    select(CryptoOption)
                    .where(CryptoOption.active.is_(True))
                    .order_by(CryptoOption.id)
                )
            )

    async def withdraw(
        self,
        user_id: int,
        amount: str,
        currency: str,
        method: str,
        option: str,
        details: str,
        request_token: str,
    ) -> Withdrawal:
        value = positive(amount, cents=True)
        async with self.sessions() as s, s.begin():
            user = await s.get(User, user_id, with_for_update=True)
            if not user or user.status != "active" or not user.currency:
                raise BusinessError("onboarding_required")
            prior = await s.scalar(
                select(Withdrawal).where(Withdrawal.request_token == request_token)
            )
            if prior:
                if prior.user_id != user_id:
                    raise BusinessError("unauthorized")
                return prior
            if currency != user.currency:
                raise BusinessError("currency_changed")
            minimum = positive(str(await configuration(s, f"minimum.{currency}", "1")))
            if value < minimum:
                raise BusinessError("below_minimum")
            if method == "card":
                if option not in {"Visa", "Mastercard", "Mir"}:
                    raise BusinessError("invalid_destination")
                details = re.sub(r"[ -]", "", details)
                if not details.isascii() or not details.isdigit() or not 13 <= len(details) <= 19:
                    raise BusinessError("invalid_destination")
                if (
                    (option == "Visa" and not details.startswith("4"))
                    or (option == "Mir" and not 2200 <= int(details[:4]) <= 2204)
                    or (
                        option == "Mastercard"
                        and not (51 <= int(details[:2]) <= 55 or 2221 <= int(details[:4]) <= 2720)
                    )
                ):
                    raise BusinessError("invalid_destination")
                digits = [int(x) for x in details]
                checksum = sum(
                    (d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2))
                    for i, d in enumerate(reversed(digits))
                )
                if checksum % 10:
                    raise BusinessError("invalid_destination")
                label = option
            elif method == "crypto":
                crypto = await s.get(CryptoOption, option)
                if not crypto or not crypto.active:
                    raise BusinessError("invalid_destination")
                patterns = {
                    "evm": r"0x[0-9a-fA-F]{40}",
                    "tron": r"T[1-9A-HJ-NP-Za-km-z]{33}",
                    "solana": r"[1-9A-HJ-NP-Za-km-z]{32,44}",
                    "ton": r"(?:(?:EQ|UQ|kQ|0Q)[A-Za-z0-9_-]{46}|-?\d:[0-9a-fA-F]{64})",
                }
                if not re.fullmatch(patterns[crypto.address_kind], details):
                    raise BusinessError("invalid_destination")
                label = f"{crypto.asset} / {crypto.network}"
            else:
                raise BusinessError("invalid_destination")
            rate = await self.rate(s, currency)
            # Reserve upward at accounting precision; never reserve less than requested.
            usd = (value / rate.value).quantize(UNIT, ROUND_UP)
            if usd > user.available_usd:
                raise BusinessError("insufficient_funds")
            withdrawal = Withdrawal(
                request_token=request_token,
                user_id=user_id,
                amount=value,
                currency=currency,
                amount_usd=usd,
                exchange_rate=rate.value,
                rate_source=rate.source,
                rate_observed_at=rate.observed_at,
                method=method,
                destination_label=label,
                encrypted_details=self.cipher.encrypt(details.encode()).decode(),
            )
            s.add(withdrawal)
            await s.flush()
            user.available_usd -= usd
            user.reserved_usd += usd
            s.add(
                Transaction(
                    user_id=user_id,
                    kind="withdraw_reserve",
                    amount_usd=usd,
                    amount=value,
                    currency=currency,
                    status="reserved",
                    withdrawal_id=withdrawal.id,
                )
            )
            audit(s, user_id, "withdraw.reserve", str(withdrawal.id), amount_usd=str(usd))
            return withdrawal

    async def transition(self, actor: int, request_id: int, target: str, reason: str = ""):
        async with self.sessions() as s, s.begin():
            await require_admin(s, actor)
            withdrawal = await s.get(Withdrawal, request_id, with_for_update=True)
            if not withdrawal:
                raise BusinessError("not_found")
            if target not in {"processing", "paid", "rejected", "cancelled"}:
                raise BusinessError("invalid_transition")
            if withdrawal.status == target:
                return withdrawal
            allowed = {
                "pending": {"processing", "paid", "rejected", "cancelled"},
                "processing": {"paid", "rejected", "cancelled"},
            }
            if target not in allowed.get(withdrawal.status, set()):
                raise BusinessError("invalid_transition")
            if target in {"rejected", "cancelled"} and not reason.strip():
                raise BusinessError("reason_required")
            user = await s.get(User, withdrawal.user_id, with_for_update=True)
            old = withdrawal.status
            if target in {"paid", "rejected", "cancelled"}:
                user.reserved_usd -= withdrawal.amount_usd
                if target == "paid":
                    user.withdrawn_usd += withdrawal.amount_usd
                    kind = "withdraw_paid"
                else:
                    user.available_usd += withdrawal.amount_usd
                    kind = "withdraw_release"
                s.add(
                    Transaction(
                        user_id=user.id,
                        kind=kind,
                        amount_usd=withdrawal.amount_usd,
                        amount=withdrawal.amount,
                        currency=withdrawal.currency,
                        status=target,
                        withdrawal_id=withdrawal.id,
                    )
                )
            withdrawal.status, withdrawal.admin_id = target, actor
            withdrawal.processed_at = datetime.now(UTC)
            withdrawal.reason = reason[:1000] or None
            audit(
                s,
                actor,
                "withdraw.transition",
                str(request_id),
                old=old,
                new=target,
                reason=reason[:1000],
            )
            return withdrawal

    async def is_admin(self, actor: int) -> bool:
        async with self.sessions() as s:
            row = await s.get(Administrator, actor)
            return bool(row and row.active)

    async def admins(self, actor: int):
        async with self.sessions() as s:
            await require_admin(s, actor)
            return list(
                await s.scalars(select(Administrator).where(Administrator.active.is_(True)))
            )

    async def change_admin(self, actor: int, target: int, active: bool):
        if target <= 0:
            raise BusinessError("invalid_input")
        async with self.sessions() as s, s.begin():
            await s.execute(text("SELECT pg_advisory_xact_lock(714202601)"))
            await require_admin(s, actor)
            admins = list(
                await s.scalars(select(Administrator).where(Administrator.active.is_(True)))
            )
            row = await s.get(Administrator, target)
            if not active and row and row.active and len(admins) <= 1:
                raise BusinessError("last_admin")
            if not row:
                row = Administrator(id=target, active=active)
                s.add(row)
            else:
                row.active = active
            audit(s, actor, "admin.enable" if active else "admin.disable", str(target))

    async def save_product(self, actor: int, data: dict):
        required = {"id", "name_ru", "name_en", "rate"}
        allowed = required | {
            "description_ru",
            "description_en",
            "conditions_ru",
            "conditions_en",
            "image",
            "active",
            "display_order",
        }
        if (
            not isinstance(data, dict)
            or set(data) - allowed
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", str(data.get("id", "")))
        ):
            raise BusinessError("invalid_input")
        values = dict(data)
        if "rate" in values:
            values["rate"] = positive(str(values["rate"]))
            if values["rate"] >= 100000000 or values["rate"] != values["rate"].quantize(UNIT):
                raise BusinessError("invalid_amount")
        for key in (
            "name_ru",
            "name_en",
            "description_ru",
            "description_en",
            "conditions_ru",
            "conditions_en",
        ):
            if key in values and (
                not isinstance(values[key], str)
                or len(values[key]) > (120 if key.startswith("name") else 600)
            ):
                raise BusinessError("invalid_input")
        if "active" in values and type(values["active"]) is not bool:
            raise BusinessError("invalid_input")
        if "display_order" in values and (
            type(values["display_order"]) is not int or abs(values["display_order"]) > 100000
        ):
            raise BusinessError("invalid_input")
        if (
            "image" in values
            and values["image"] is not None
            and (not isinstance(values["image"], str) or len(values["image"]) > 512)
        ):
            raise BusinessError("invalid_input")
        async with self.sessions() as s, s.begin():
            await require_admin(s, actor)
            row = await s.get(Product, values["id"], with_for_update=True)
            if not row:
                if (
                    not required <= values.keys()
                    or not values["name_ru"].strip()
                    or not values["name_en"].strip()
                ):
                    raise BusinessError("invalid_input")
                row = Product(**values)
                s.add(row)
            else:
                for key, value in values.items():
                    if key.startswith("name") and not value.strip():
                        raise BusinessError("invalid_input")
                    setattr(row, key, value)
            audit(s, actor, "product.save", values["id"], fields=sorted(values))
            return row

    async def set_config(self, actor: int, key: str, value: Any):
        valid = False
        parts = key.split(".")
        if len(parts) == 2 and parts[0] in CONTENT_KEYS and parts[1] in {"ru", "en"}:
            valid = isinstance(value, str) and len(value) <= 700
            if valid and parts[0].endswith("_url") and value:
                parsed = urlsplit(value)
                valid = (
                    parsed.scheme == "https"
                    and bool(parsed.hostname)
                    and not parsed.username
                    and not parsed.password
                )
            if valid and parts[0] == "support_contact" and value:
                valid = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", value.lstrip("@")))
        elif key.startswith("image.") and key[6:] in SCREENS:
            valid = value is None or isinstance(value, str) and len(value) <= 512
        elif key in {"minimum.USD", "minimum.RUB"}:
            value = str(positive(str(value), cents=True))
            valid = True
        elif key == "exchange.url":
            parsed = urlsplit(str(value))
            valid = (
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and not parsed.username
                and not parsed.password
            )
        elif key == "exchange.ttl":
            valid = type(value) is int and 1 <= value <= 86400
        elif key.startswith("message.") and parts[-1] in {"ru", "en"}:
            from app.locales import MESSAGES

            message_key = ".".join(parts[1:-1])
            valid = (
                message_key in MESSAGES[parts[-1]]
                and isinstance(value, str)
                and len(value) <= 700
                and "{" not in value
                and "}" not in value
            )
        if not valid:
            raise BusinessError("invalid_input")
        async with self.sessions() as s, s.begin():
            await require_admin(s, actor)
            row = await s.get(Configuration, key, with_for_update=True)
            if row:
                row.value, row.updated_by = value, actor
            else:
                s.add(Configuration(key=key, value=value, updated_by=actor))
            audit(s, actor, "configuration.save", key)

    async def save_crypto(self, actor: int, data: dict):
        allowed = {"id", "asset", "network", "address_kind", "active"}
        if (
            not isinstance(data, dict)
            or set(data) - allowed
            or not re.fullmatch(r"[a-z0-9_]{1,32}", str(data.get("id", "")))
        ):
            raise BusinessError("invalid_input")
        if "active" in data and type(data["active"]) is not bool:
            raise BusinessError("invalid_input")
        if "address_kind" in data and data["address_kind"] not in {"evm", "tron", "solana", "ton"}:
            raise BusinessError("invalid_input")
        for field, limit in [("asset", 16), ("network", 32)]:
            if field in data and (
                not isinstance(data[field], str) or not 1 <= len(data[field]) <= limit
            ):
                raise BusinessError("invalid_input")
        async with self.sessions() as s, s.begin():
            await require_admin(s, actor)
            row = await s.get(CryptoOption, data["id"], with_for_update=True)
            if not row:
                if not {"asset", "network", "address_kind"} <= data.keys():
                    raise BusinessError("invalid_input")
                s.add(CryptoOption(**data))
            else:
                for key, value in data.items():
                    setattr(row, key, value)
            audit(s, actor, "crypto.save", data["id"])

    async def history(self, user_id: int, kind: str, page: int):
        if kind not in {"keys", "transactions", "withdrawals"} or not 0 <= page <= 100000:
            raise BusinessError("invalid_input")
        model = {"keys": AcceptedKey, "transactions": Transaction, "withdrawals": Withdrawal}[kind]
        async with self.sessions() as s:
            return list(
                await s.scalars(
                    select(model)
                    .where(model.user_id == user_id)
                    .order_by(model.id.desc())
                    .offset(page * 5)
                    .limit(6)
                )
            )

    async def admin_withdrawals(self, actor: int, page: int = 0):
        async with self.sessions() as s:
            await require_admin(s, actor)
            return list(
                await s.scalars(
                    select(Withdrawal)
                    .where(Withdrawal.status.in_(["pending", "processing"]))
                    .order_by(Withdrawal.id)
                    .offset(page * 5)
                    .limit(6)
                )
            )

    async def withdrawal_details(self, actor: int, request_id: int):
        async with self.sessions() as s, s.begin():
            await require_admin(s, actor)
            row = await s.get(Withdrawal, request_id)
            if not row:
                raise BusinessError("not_found")
            audit(s, actor, "withdraw.details", str(request_id))
            return row, self.cipher.decrypt(row.encrypted_details.encode()).decode()

    async def inspect_user(self, actor: int, user_id: int):
        async with self.sessions() as s:
            await require_admin(s, actor)
            row = await s.get(User, user_id)
            if not row:
                raise BusinessError("not_found")
            keys = list(
                await s.scalars(
                    select(AcceptedKey)
                    .where(AcceptedKey.user_id == user_id)
                    .order_by(AcceptedKey.id.desc())
                    .limit(5)
                )
            )
            return row, keys

    async def dashboard(self, actor: int, days: int = 30):
        if not 1 <= days <= 3650:
            raise BusinessError("invalid_input")
        since = datetime.now(UTC) - timedelta(days=days)
        async with self.sessions() as s:
            await require_admin(s, actor)

            async def count(model, *where):
                return await s.scalar(select(func.count()).select_from(model).where(*where))

            async def total(column, *where):
                return await s.scalar(select(func.coalesce(func.sum(column), 0)).where(*where))

            return {
                "users": await count(User),
                "new_users": await count(User, User.registered_at >= since),
                "active_users": await count(User, User.last_active_at >= since),
                "accepted": await count(AcceptedKey, AcceptedKey.created_at >= since),
                "credited_usd": str(
                    await total(AcceptedKey.payment_usd, AcceptedKey.created_at >= since)
                ),
                "pending_usd": str(
                    await total(
                        Withdrawal.amount_usd, Withdrawal.status.in_(["pending", "processing"])
                    )
                ),
                "paid_usd": str(
                    await total(
                        Withdrawal.amount_usd,
                        Withdrawal.status == "paid",
                        Withdrawal.processed_at >= since,
                    )
                ),
                "pending_count": await count(
                    Withdrawal, Withdrawal.status.in_(["pending", "processing"])
                ),
                "available_usd": str(await total(User.available_usd)),
                "reserved_usd": str(await total(User.reserved_usd)),
                "failed": await count(
                    VerificationAttempt,
                    VerificationAttempt.outcome != "credited",
                    VerificationAttempt.created_at >= since,
                ),
                "by_provider": [
                    list(map(str, row))
                    for row in (
                        await s.execute(
                            select(
                                AcceptedKey.product_id,
                                func.count(),
                                func.sum(AcceptedKey.payment_usd),
                            )
                            .where(AcceptedKey.created_at >= since)
                            .group_by(AcceptedKey.product_id)
                        )
                    ).all()
                ],
                "by_currency": [
                    list(map(str, row))
                    for row in (
                        await s.execute(
                            select(AcceptedKey.currency, func.sum(AcceptedKey.credited_amount))
                            .where(AcceptedKey.created_at >= since)
                            .group_by(AcceptedKey.currency)
                        )
                    ).all()
                ],
                "recent": [
                    {
                        "actor": row.actor_id,
                        "event": row.event,
                        "entity": row.entity,
                        "at": row.created_at.isoformat(),
                    }
                    for row in await s.scalars(
                        select(AuditLog).order_by(AuditLog.id.desc()).limit(5)
                    )
                ],
            }

    async def admins_for_notifications(self):
        async with self.sessions() as s:
            return list(
                await s.scalars(select(Administrator).where(Administrator.active.is_(True)))
            )
