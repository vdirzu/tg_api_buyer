import logging
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from app.locales import tr

logger = logging.getLogger(__name__)


def keyboard(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, url=target[4:])
                if target.startswith("url:")
                else InlineKeyboardButton(text=label, callback_data=target)
                for label, target in row
            ]
            for row in rows
        ]
    )


def navigation(lang, back="home"):
    return [[(tr(lang, "back"), back), (tr(lang, "home"), "home")]]


async def render(event: CallbackQuery | Message, text: str, rows=(), image=None):
    message = event.message if isinstance(event, CallbackQuery) else event
    markup = keyboard(rows) if rows else None
    # Long financial/history screens remain text; send the configured image separately.
    if image and len(text) > 1024:
        await message.answer_photo(image)
        image = None
    if isinstance(event, CallbackQuery):
        try:
            if image and message.photo:
                return await message.edit_media(
                    InputMediaPhoto(media=image, caption=text), reply_markup=markup
                )
            if not image and not message.photo:
                return await message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as error:
            if "message is not modified" in str(error):
                return message
            # Messages too old to edit are safely replaced below.
        if image:
            result = await message.answer_photo(image, caption=text, reply_markup=markup)
        else:
            result = await message.answer(text, reply_markup=markup)
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return result
    if image:
        return await message.answer_photo(image, caption=text, reply_markup=markup)
    return await message.answer(text, reply_markup=markup)


async def delete_sensitive(message: Message):
    try:
        await message.delete()
    except TelegramBadRequest:
        logger.warning("sensitive_message_delete_failed", extra={"user_id": message.from_user.id})


def content(config, lang, key, fallback=None):
    return config.get(f"{key}.{lang}", fallback if fallback is not None else tr(lang, key))


def message_text(config, lang, key):
    return config.get(f"message.{key}.{lang}", tr(lang, key))
