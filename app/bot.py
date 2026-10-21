from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from app.handlers import admin, menus, onboarding, verification, withdrawals
from app.middlewares import ContextMiddleware


def make_dispatcher(market):
    # Single polling worker. Durable financial state lives in PostgreSQL.
    dispatcher = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    dispatcher.message.outer_middleware(ContextMiddleware(market))
    dispatcher.callback_query.outer_middleware(ContextMiddleware(market))
    for router in (
        onboarding.router,
        admin.router,
        menus.router,
        verification.router,
        withdrawals.router,
    ):
        dispatcher.include_router(router)
    return dispatcher
