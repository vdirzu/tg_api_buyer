import logging

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from app.handlers.ui import keyboard, message_text, navigation
from app.locales import tr
from app.services.errors import BusinessError

logger = logging.getLogger(__name__)


class ContextMiddleware(BaseMiddleware):
    def __init__(self, market):
        self.market = market

    async def __call__(self, handler, event, data):
        if not isinstance(event, (Message, CallbackQuery)) or not event.from_user:
            return
        message = event.message if isinstance(event, CallbackQuery) else event
        # A private chat binds callbacks and FSM state to its owner.
        if not message or message.chat.type != "private" or message.chat.id != event.from_user.id:
            if isinstance(event, CallbackQuery):
                await event.answer()
            return
        user = None
        try:
            user = await self.market.user(event.from_user.id)
            if isinstance(event, CallbackQuery) and (not user.language or not user.currency):
                permitted = event.data in {"home", "language", "currency"} or event.data.startswith(
                    ("lang:", "currency:")
                )
                if not permitted:
                    raise BusinessError("onboarding_required")
            data.update(market=self.market, user=user)
            return await handler(event, data)
        except BusinessError as error:
            lang = user.language if user else "en"
            config = await self.market.settings()
            text = message_text(config, lang, error.code)
            rows = navigation(lang)
            if error.code == "rate_unavailable":
                rows.insert(0, [(tr(lang, "retry_pending"), "retry_pending")])
            await message.answer(text, reply_markup=keyboard(rows))
            logger.info(
                "business_rejection", extra={"code": error.code, "user_id": event.from_user.id}
            )
        except (ValueError, KeyError, TypeError):
            await message.answer(tr(user.language if user else "en", "invalid_input"))
        except Exception as error:
            # No exception strings, Update dumps or traceback locals: they can contain keys/details.
            logger.error(
                "handler_failed",
                extra={"error_type": type(error).__name__, "user_id": event.from_user.id},
            )
            await message.answer(tr(user.language if user else "en", "generic_error"))
        finally:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except TelegramAPIError:
                    pass
