import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx

from app.services.errors import BusinessError


@dataclass(frozen=True)
class Rate:
    value: Decimal
    source: str
    observed_at: datetime


class ExchangeRates:
    def __init__(self, url: str, ttl: int = 3600):
        self.url, self.ttl = url, ttl
        self._cache: tuple[str, float, Rate] | None = None
        self._lock = asyncio.Lock()

    async def get(self, currency: str, url: str | None = None, ttl: int | None = None) -> Rate:
        if currency == "USD":
            return Rate(Decimal(1), "USD accounting", datetime.now(UTC))
        if currency != "RUB":
            raise BusinessError("invalid_currency")
        endpoint, lifetime = url or self.url, min(ttl or self.ttl, 86400)
        parsed = urlsplit(endpoint)
        # Administrator-controlled URL; HTTPS and redirects disabled. Restrict egress in deployment.
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise BusinessError("rate_unavailable")
        async with self._lock:
            if (
                self._cache
                and self._cache[0] == endpoint
                and time.monotonic() - self._cache[1] < lifetime
            ):
                return self._cache[2]
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                    response = await client.get(endpoint)
                    response.raise_for_status()
                    data = response.json(parse_float=Decimal)
                value = Decimal(str(data["rates"]["RUB"]))
                observed = datetime.fromtimestamp(int(data["time_last_update_unix"]), UTC)
                if (
                    not value.is_finite()
                    or not Decimal("0.01") < value < Decimal("1000000")
                    or data.get("base_code") != "USD"
                    or data.get("result") != "success"
                    or datetime.now(UTC) - observed > timedelta(hours=48)
                    or observed > datetime.now(UTC) + timedelta(minutes=5)
                ):
                    raise ValueError
                result = Rate(value.quantize(Decimal("0.00000001")), endpoint, observed)
                self._cache = (endpoint, time.monotonic(), result)
                return result
            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                TypeError,
                InvalidOperation,
                OverflowError,
            ):
                raise BusinessError("rate_unavailable") from None
