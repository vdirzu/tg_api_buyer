import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.services.errors import BusinessError
from app.services.exchange_rates import ExchangeRates


async def test_malformed_csv_recovery(market):
    original = market.verifier.path.read_text()
    for malformed in [
        "bad,header\n1,2",
        original.replace("100.00", "NaN", 1),
        original + original.splitlines()[1] + "\n",
    ]:
        market.verifier.path.write_text(malformed)
        with pytest.raises(BusinessError, match="csv_unavailable"):
            await market.accept(10, "a", "key-1")
        assert (await market.user(10)).available_usd == 0
    market.verifier.path.write_text(original)
    assert (await market.accept(10, "a", "key-1")).payment_usd == 30


async def test_missing_csv_never_credits(market):
    market.verifier.path.unlink()
    with pytest.raises(BusinessError, match="csv_unavailable"):
        await market.accept(10, "a", "key-1")
    assert (await market.user(10)).accepted_count == 0


async def test_exchange_http_cache_failure_recovery(monkeypatch):
    calls = []
    state = {"fail": True, "stale": False}
    real_client = httpx.AsyncClient

    def respond(request):
        calls.append(request)
        if state["fail"]:
            return httpx.Response(503)
        observed = datetime.now(UTC) - (timedelta(days=3) if state["stale"] else timedelta())
        return httpx.Response(
            200,
            text=json.dumps(
                {
                    "result": "success",
                    "base_code": "USD",
                    "rates": {"RUB": 92.37},
                    "time_last_update_unix": int(observed.timestamp()),
                }
            ),
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw)
    )
    rates = ExchangeRates("https://open.er-api.com/v6/latest/USD", 10)
    with pytest.raises(BusinessError, match="rate_unavailable"):
        await rates.get("RUB")
    state["fail"] = False
    first = await rates.get("RUB")
    second = await rates.get("RUB")
    assert str(first.value) == "92.37000000" and first == second and len(calls) == 2
    rates._cache = None
    state["stale"] = True
    with pytest.raises(BusinessError, match="rate_unavailable"):
        await rates.get("RUB")
    assert (await rates.get("USD")).value == 1
