import asyncio
import selectors

import pytest

from app import runtime


def test_runtime_executes_coroutine():
    async def work():
        await asyncio.sleep(0)
        return 42

    assert runtime.run_async(work()) == 42


def test_windows_uses_selector_loop(monkeypatch):
    monkeypatch.setattr(runtime, "platform", "win32")

    async def check_loop():
        loop = asyncio.get_running_loop()
        assert isinstance(loop, asyncio.SelectorEventLoop)
        assert isinstance(loop._selector, selectors.SelectSelector)
        await asyncio.sleep(0)
        return "completed"

    assert runtime.run_async(check_loop()) == "completed"


def test_runtime_propagates_errors():
    async def fail():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        runtime.run_async(fail())
