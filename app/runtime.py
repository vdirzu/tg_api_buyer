"""Async entry point shared by the bot, CLI and migrations."""

import asyncio
import selectors
from sys import platform
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coroutine: Coroutine[Any, Any, T]) -> T:
    if platform == "win32":
        # Psycopg async connections cannot run on Windows' default ProactorEventLoop.
        # loop_factory avoids deprecated global event-loop policies (Python 3.14+).
        return asyncio.run(
            coroutine,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coroutine)
