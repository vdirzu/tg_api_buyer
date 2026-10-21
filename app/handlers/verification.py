import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.states import Flow
from app.handlers.ui import delete_sensitive, message_text, navigation, render
from app.locales import tr
from app.services.errors import BusinessError

router = Router()


@router.callback_query(F.data.startswith("submit:"))
async def begin(event: CallbackQuery, state: FSMContext, market, user):
    product = await market.product(event.data.split(":", 1)[1])
    await state.set_state(Flow.key)
    await state.update_data(product_id=product.id)
    await render(
        event, tr(user.language, "enter_key"), navigation(user.language, f"product:{product.id}")
    )


async def result(event, accepted, market, user):
    user = await market.user(user.id)
    lang = user.language
    text = (
        f"{tr(lang, 'credited')}: {accepted.credited_amount} {accepted.currency}\n"
        f"{tr(lang, 'keys_balance')}: {accepted.balance_usd}\n"
        f"{tr(lang, 'price')}: {accepted.purchase_rate}\n"
        f"{tr(lang, 'discount')}: {accepted.discount * 100:.0f}%\n"
        f"{tr(lang, 'keys_region')}: {tr(lang, 'yes' if accepted.csv_region_restricted else 'no')}\n"
        f"{tr(lang, 'keys_test_region')}: {tr(lang, 'yes' if accepted.test_region_restricted else 'no')}\n"
        f"FX: {accepted.exchange_rate}\n"
    )
    try:
        _, balance = await market.shown_balance(user)
        text += f"{tr(lang, 'balance')}: {balance} {user.currency}"
    except BusinessError:
        text += f"{tr(lang, 'balance')}: {user.available_usd} USD"
    await render(
        event,
        text,
        [[(tr(lang, "catalog"), "catalog"), (tr(lang, "profile"), "profile")]] + navigation(lang),
    )


@router.message(Flow.key, F.text)
async def submit(message: Message, state: FSMContext, market, user):
    data = await state.get_data()
    product_id = data["product_id"]
    config, lang = await market.settings(), user.language
    key = message.text
    await delete_sensitive(message)
    progress = await message.answer(message_text(config, lang, "progress_lookup"))

    async def update(stage, value):
        text = message_text(config, lang, stage)
        if stage == "progress_region":
            text += "\n" + tr(lang, "keys_region") + ": " + tr(lang, "yes" if value else "no")
        elif value is not None:
            text += ": " + str(value)
        try:
            await progress.edit_text(text)
        except TelegramAPIError:
            logging.getLogger(__name__).warning(
                "progress_update_failed", extra={"user_id": user.id}
            )

    accepted = await market.accept(user.id, product_id, key, progress=update)
    await state.clear()
    try:
        await progress.delete()
    except TelegramAPIError:
        logging.getLogger(__name__).warning("progress_delete_failed", extra={"user_id": user.id})
    await result(message, accepted, market, user)


@router.callback_query(F.data == "retry_pending")
async def retry(event: CallbackQuery, state: FSMContext, market, user):
    accepted = await market.retry_pending(user.id)
    await state.clear()
    await result(event, accepted, market, user)
