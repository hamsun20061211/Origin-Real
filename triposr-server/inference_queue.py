"""FIFO-style single-flight GPU inference with visible queue depth."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import torch

_lock = asyncio.Lock()
_waiting_for_lock: int = 0
_running: bool = False


def queue_snapshot() -> dict:
    return {
        "waiting_jobs": _waiting_for_lock,
        "running": _running,
        "queued_total": _waiting_for_lock + (1 if _running else 0),
    }


@asynccontextmanager
async def generation_slot() -> AsyncIterator[None]:
    global _waiting_for_lock, _running
    acquired_inner = False
    _waiting_for_lock += 1
    try:
        async with _lock:
            _waiting_for_lock -= 1
            acquired_inner = True
            _running = True
            try:
                yield
            finally:
                _running = False
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
    finally:
        if not acquired_inner:
            _waiting_for_lock -= 1
