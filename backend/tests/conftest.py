import asyncio
import os

import pytest


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def _reset_config():
    """Reset config singleton between tests."""
    from src.config import reset_config
    reset_config()
    yield
    reset_config()


@pytest.fixture
def event_queue():
    return asyncio.Queue()
