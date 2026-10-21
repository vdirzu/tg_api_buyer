import asyncio
import csv
import hashlib
import hmac
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.services.errors import BusinessError


def fingerprint(key: str, secret: str) -> str:
    return hmac.new(secret.encode(), key.strip().encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Record:
    provider_id: str
    balance_usd: Decimal
    region_restricted: bool
    test_status: str


class CSVVerifier:
    def __init__(self, path: Path, secret: str):
        self.path, self.secret = path, secret

    def _read(self) -> dict[str, Record]:
        try:
            # Read a single stable snapshot. Writers must use atomic os.replace.
            with self.path.open("rb") as stream:
                before = self.path.stat()
                raw = stream.read(10_000_001)
                after = self.path.stat()
            if len(raw) > 10_000_000 or (before.st_ino, before.st_mtime_ns, before.st_size) != (
                after.st_ino,
                after.st_mtime_ns,
                after.st_size,
            ):
                raise ValueError
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            expected = {
                "key_fingerprint",
                "provider_id",
                "balance_usd",
                "region_restricted",
                "test_status",
            }
            if set(reader.fieldnames or []) != expected or len(reader.fieldnames or []) != 5:
                raise ValueError
            records = {}
            for row in reader:
                if set(row) != expected or any(value is None for value in row.values()):
                    raise ValueError
                fp = row["key_fingerprint"]
                balance = Decimal(row["balance_usd"])
                if (
                    not re.fullmatch(r"[0-9a-f]{64}", fp)
                    or fp in records
                    or not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", row["provider_id"])
                    or not balance.is_finite()
                    or balance < 0
                    or balance > Decimal("1000000000")
                    or balance != balance.quantize(Decimal("0.00000001"))
                    or row["region_restricted"] not in {"true", "false"}
                    or row["test_status"] not in {"valid", "invalid", "ineligible"}
                ):
                    raise ValueError
                records[fp] = Record(
                    row["provider_id"],
                    balance,
                    row["region_restricted"] == "true",
                    row["test_status"],
                )
            return records
        except (
            OSError,
            UnicodeError,
            ValueError,
            InvalidOperation,
            KeyError,
            TypeError,
            csv.Error,
        ):
            raise BusinessError("csv_unavailable") from None

    async def lookup(self, key: str, provider: str) -> tuple[str, Record]:
        if not key.strip() or len(key) > 4096:
            raise BusinessError("key_not_found")
        records = await asyncio.to_thread(self._read)
        fp = fingerprint(key, self.secret)
        record = records.get(fp)
        if record is None:
            raise BusinessError("key_not_found")
        if record.provider_id != provider:
            raise BusinessError("wrong_provider")
        if record.test_status != "valid" or record.balance_usd <= 0:
            raise BusinessError("invalid_key")
        return fp, record
