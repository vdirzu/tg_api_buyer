from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.ui import content, navigation, render
from app.locales import tr
from app.services.errors import BusinessError

router = Router()


async def language_screen(event, lang="en"):
    await render(
        event,
        tr(lang, "choose_language"),
        [[("Русский", "lang:ru"), ("English", "lang:en")]] + navigation(lang),
    )


async def currency_screen(event, lang):
    await render(
        event,
        tr(lang, "choose_currency"),
        [[("USD", "currency:USD"), ("RUB", "currency:RUB")]] + navigation(lang),
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, market, user):
    await state.clear()
    if not user.language:
        await language_screen(message)
    elif not user.currency:
        await currency_screen(message, user.language)
    else:
        from app.handlers.menus import home

        await home(message, state, market, user)


@router.callback_query(F.data == "language")
async def change_language(event: CallbackQuery, user):
    await language_screen(event, user.language)


@router.callback_query(F.data.startswith("lang:"))
async def language(event: CallbackQuery, market, user):
    lang = event.data.split(":", 1)[1]
    if lang not in {"ru", "en"}:
        raise BusinessError("invalid_input")
    await market.preferences(user.id, language=lang)
    config = await market.settings()
    await render(
        event,
        content(config, lang, "welcome"),
        [[("USD", "currency:USD"), ("RUB", "currency:RUB")]] + navigation(lang),
        config.get("image.welcome"),
    )


@router.callback_query(F.data == "currency")
async def change_currency(event: CallbackQuery, user):
    await currency_screen(event, user.language)


@router.callback_query(F.data.startswith("currency:"))
async def currency(event: CallbackQuery, state: FSMContext, market, user):
    if not user.language:
        return await language_screen(event)
    value = event.data.split(":", 1)[1]
    await market.preferences(user.id, currency=value)
    from app.handlers.menus import home

    await home(event, state, market, await market.user(user.id))
