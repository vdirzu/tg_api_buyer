from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, DeleteMessage, GetMe
from aiogram.types import CallbackQuery, Chat, Message, Update, User as TelegramUser

from app.bot import make_dispatcher


class TelegramStub(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests = []
        self.serial = 100

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b""

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, (AnswerCallbackQuery, DeleteMessage)):
            return True
        if isinstance(method, GetMe):
            return TelegramUser(id=999, is_bot=True, first_name="Test", username="test_bot")
        self.serial += 1
        return Message(
            message_id=self.serial,
            date=datetime.now(UTC),
            chat=Chat(id=int(method.chat_id), type="private"),
            text=getattr(method, "text", None),
            caption=getattr(method, "caption", None),
            reply_markup=getattr(method, "reply_markup", None),
        ).as_(bot)


async def test_full_telegram_flow_with_stubbed_api(market, card):
    stub = TelegramStub()
    bot = Bot("123456:synthetic-test-token", session=stub)
    dp = make_dispatcher(market)
    serial = 0

    async def message(text, who=20, photo=None, caption=None):
        nonlocal serial
        serial += 1
        msg = Message(
            message_id=serial,
            date=datetime.now(UTC),
            chat=Chat(id=who, type="private"),
            from_user=TelegramUser(id=who, is_bot=False, first_name="Synthetic"),
            text=text,
            photo=photo,
            caption=caption,
        )
        await dp.feed_update(bot, Update(update_id=serial, message=msg))

    async def callback(value, who=20):
        nonlocal serial
        serial += 1
        msg = Message(
            message_id=serial,
            date=datetime.now(UTC),
            chat=Chat(id=who, type="private"),
            text="Menu",
        )
        cb = CallbackQuery(
            id=str(serial),
            from_user=TelegramUser(id=who, is_bot=False, first_name="Synthetic"),
            chat_instance="test",
            message=msg,
            data=value,
        )
        await dp.feed_update(bot, Update(update_id=serial, callback_query=cb))

    def last_text():
        return next(
            (getattr(r, "text", "") for r in reversed(stub.requests) if getattr(r, "text", None)),
            "",
        )

    await message("/start")
    assert "Choose language" in last_text()
    await callback("lang:ru")
    assert "Добро пожаловать" in last_text()
    await callback("currency:USD")
    assert (await market.user(20)).language == "ru"
    assert (await market.user(20)).currency == "USD"
    await callback("catalog")
    await callback("product:a")
    assert "Провайдер A" in last_text()
    await callback("submit:a")
    await callback("support")  # Does not cancel key submission.
    await message("key-1")
    assert (await market.user(20)).available_usd == 30
    assert "Начислено" in last_text()
    await callback("profile")
    assert "30.00 USD" in last_text()
    await callback("history:keys:0")
    assert "100.00000000" in last_text()
    await callback("withdraw")
    await callback("method:card")
    await callback("destination:card:Visa")
    await message("10")
    await message(card)
    assert (await market.user(20)).reserved_usd == 10
    assert "Заявка создана" in last_text()
    await callback("admin")
    assert "Нет доступа" in last_text()
    await market.user(1)
    await market.preferences(1, language="en", currency="USD")
    await callback("admin", 1)
    assert "Administration" in last_text()
    await callback("ad:products", 1)
    await message('{"id":"a","rate":"0.4","name_en":"Edited"}', 1)
    assert (await market.product("a")).rate.as_tuple().digits[0] == 4
    await callback("ad:image", 1)
    await message(
        None,
        1,
        photo=[
            {"file_id": "telegram_photo", "file_unique_id": "photo1", "width": 100, "height": 100}
        ],
        caption="main",
    )
    assert (await market.settings())["image.main"] == "telegram_photo"
    await callback("ad:withdrawals:0", 1)
    requests = await market.admin_withdrawals(1)
    request = requests[0]
    await callback(f"ad:action:{request.id}:rejected", 1)
    await message("Synthetic rejection", 1)
    assert (await market.user(20)).available_usd == 30
    assert (await market.user(20)).reserved_usd == 0
    await callback("ad:stats:7", 1)
    assert "Accepted keys in period: 1" in last_text()
    await dp.storage.close()
    await bot.session.close()
