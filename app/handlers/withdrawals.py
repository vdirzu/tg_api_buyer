import logging
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.states import Flow
from app.handlers.ui import content, delete_sensitive, keyboard, navigation, render
from app.locales import tr
from app.services.errors import BusinessError
from app.services.pricing import positive

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "withdraw")
async def begin(event: CallbackQuery, state: FSMContext, market, user):
    await state.clear()
    lang, config = user.language, await market.settings()
    text = content(config, lang, "withdraw", tr(lang, "choose_method"))
    await render(
        event,
        text,
        [[(tr(lang, "card"), "method:card"), (tr(lang, "crypto"), "method:crypto")]]
        + navigation(lang, "profile"),
        config.get("image.withdraw"),
    )


@router.callback_query(F.data.startswith("method:"))
async def method(event: CallbackQuery, state: FSMContext, market, user):
    value = event.data.split(":", 1)[1]
    if value not in {"card", "crypto"}:
        raise BusinessError("invalid_input")
    await state.clear()
    await state.update_data(method=value)
    if value == "card":
        rows = [[(name, f"destination:card:{name}")] for name in ("Visa", "Mastercard", "Mir")]
    else:
        rows = [
            [(f"{o.asset} / {o.network}", f"destination:crypto:{o.id}")]
            for o in await market.crypto_options()
        ]
    await render(
        event, tr(user.language, "choose_option"), rows + navigation(user.language, "withdraw")
    )


@router.callback_query(F.data.startswith("destination:"))
async def destination(event: CallbackQuery, state: FSMContext, market, user):
    _, method_name, option = event.data.split(":")
    if method_name not in {"card", "crypto"}:
        raise BusinessError("invalid_input")
    await state.set_state(Flow.withdraw_amount)
    await state.update_data(
        method=method_name, option=option, currency=user.currency, request_token=str(uuid4())
    )
    config = await market.settings()
    minimum = config.get(f"minimum.{user.currency}", "1")
    await render(
        event,
        f"{tr(user.language, 'enter_amount')}: {minimum} {user.currency}",
        navigation(user.language, "withdraw"),
    )


@router.message(Flow.withdraw_amount, F.text)
async def amount(message: Message, state: FSMContext, market, user):
    value = positive(message.text, cents=True)
    config = await market.settings()
    minimum = positive(str(config.get(f"minimum.{user.currency}", "1")))
    if value < minimum:
        raise BusinessError("below_minimum")
    _, available = await market.shown_balance(user)
    if value > available:
        raise BusinessError("insufficient_funds")
    await state.update_data(amount=str(value))
    await state.set_state(Flow.withdraw_destination)
    await render(
        message, tr(user.language, "enter_destination"), navigation(user.language, "withdraw")
    )


async def notify_admins(bot, market, withdrawal):
    from app.handlers.admin import withdrawal_rows, withdrawal_summary

    # Recheck every recipient's active authorization, including changes since startup.
    delivered = 0
    for admin in await market.admins_for_notifications():
        if not await market.is_admin(admin.id):
            continue
        profile = await market.user(admin.id)
        lang = profile.language or "en"
        try:
            await bot.send_message(
                admin.id,
                withdrawal_summary(withdrawal, lang),
                reply_markup=keyboard(withdrawal_rows(withdrawal, lang)),
            )
            delivered += 1
        except TelegramAPIError:
            logger.warning(
                "admin_notification_failed",
                extra={"admin_id": admin.id, "withdrawal_id": withdrawal.id},
            )
    return delivered


@router.message(Flow.withdraw_destination, F.text)
async def details(message: Message, state: FSMContext, market, user, bot):
    data = await state.get_data()
    await delete_sensitive(message)
    withdrawal = await market.withdraw(
        user.id,
        data["amount"],
        data["currency"],
        data["method"],
        data["option"],
        message.text.strip(),
        data["request_token"],
    )
    await state.clear()
    delivered = await notify_admins(bot, market, withdrawal)
    text = f"{tr(user.language, 'withdraw_created')}\n#{withdrawal.id} · {withdrawal.amount} {withdrawal.currency}"
    if not delivered:
        text += "\n" + tr(user.language, "notification_retry")
    await render(message, text, navigation(user.language, "profile"))
