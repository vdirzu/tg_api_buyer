from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.services.errors import BusinessError

CENT = Decimal("0.01")
UNIT = Decimal("0.00000001")


def positive(value: str | Decimal, *, cents: bool = False) -> Decimal:
    try:
        result = Decimal(value)
        if not result.is_finite() or result <= 0 or result > Decimal("1000000000"):
            raise ValueError
        if cents and result != result.quantize(CENT):
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise BusinessError("invalid_amount") from None


def payment(balance: Decimal, rate: Decimal, accepted_count: int) -> tuple[Decimal, Decimal]:
    discount = Decimal("0.20") if accepted_count == 1 else Decimal("0")
    return (balance * rate * (1 - discount)).quantize(CENT, ROUND_HALF_UP), discount


def display_amount(usd: Decimal, rate: Decimal) -> Decimal:
    return (usd * rate).quantize(CENT, ROUND_HALF_UP)
