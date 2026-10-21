import asyncio
import json
import logging
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from app.bot import make_dispatcher
from app.config import Settings
from app.database.session import make_database
from app.services.csv_verification import CSVVerifier
from app.services.exchange_rates import ExchangeRates
from app.services.marketplace import Marketplace


class JSONFormatter(logging.Formatter):
    def format(self, record):
        result = {
            "at": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        for key in ("user_id", "admin_id", "withdrawal_id", "error_type", "code"):
            if hasattr(record, key):
                result[key] = getattr(record, key)
        return json.dumps(result, ensure_ascii=False)


def build_market(settings: Settings):
    engine, sessions = make_database(settings.database_url)
    market = Marketplace(
        sessions,
        CSVVerifier(settings.csv_path, settings.key_hmac_secret.get_secret_value()),
        ExchangeRates(settings.exchange_rate_url, settings.exchange_rate_ttl_seconds),
        settings.payment_encryption_key.get_secret_value(),
        settings.submission_interval_seconds,
    )
    return engine, market


async def main():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(handlers=[handler], level=logging.INFO)
    # Third-party debug/HTTP output must not expose token-bearing Telegram URLs.
    for name in ("httpx", "httpcore", "aiohttp", "aiogram"):
        logging.getLogger(name).setLevel(logging.WARNING)
    settings = Settings()
    if not settings.bot_token.get_secret_value():
        raise SystemExit(
            "Set BOT_TOKEN securely in .env/environment before starting Telegram polling."
        )
    engine, market = build_market(settings)
    bot = Bot(settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=None))
    try:
        await market.bootstrap(settings.admin_ids)
        await bot.set_my_commands([BotCommand(command="start", description="Start / Начать")])
        await make_dispatcher(market).start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
