"""Bounded execution of native document code in spawned child processes."""

from __future__ import annotations

import asyncio
import multiprocessing
import queue
import time
from collections.abc import Callable
from multiprocessing.process import BaseProcess
from typing import Any


class IsolatedProcessError(RuntimeError):
    """A stable error for child startup, crash, or invalid output."""


class IsolatedProcessTimeoutError(IsolatedProcessError):
    """Raised after the child is terminated at its deadline."""


def _execute_child(
    result_queue: Any,
    target: Callable[..., object],
    args: tuple[object, ...],
) -> None:
    try:
        result = target(*args)
    except BaseException:
        result_queue.put(("error", None))
    else:
        result_queue.put(("ok", result))


class SpawnProcessRunner:
    """Run one picklable callable with a bounded result and hard deadline."""

    def __init__(self, *, poll_interval_seconds: float = 0.05) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._poll_interval_seconds = poll_interval_seconds

    async def run(
        self,
        target: Callable[..., object],
        args: tuple[object, ...],
        *,
        timeout_seconds: float,
    ) -> object:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue(maxsize=1)
        process = context.Process(
            target=_execute_child,
            args=(result_queue, target, args),
            daemon=False,
        )
        started = False

        try:
            try:
                process.start()
                started = True
            except Exception as error:
                raise IsolatedProcessError(
                    "The isolated process could not be started"
                ) from error

            deadline = time.monotonic() + timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await _terminate_and_join(process)
                    raise IsolatedProcessTimeoutError(
                        "The isolated process timed out"
                    )
                try:
                    status, payload = await asyncio.to_thread(
                        result_queue.get,
                        True,
                        min(self._poll_interval_seconds, remaining),
                    )
                    break
                except queue.Empty:
                    if not process.is_alive():
                        await asyncio.to_thread(process.join)
                        raise IsolatedProcessError("The isolated process failed")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await _terminate_and_join(process)
                raise IsolatedProcessTimeoutError("The isolated process timed out")
            await asyncio.to_thread(process.join, remaining)
            if process.is_alive():
                await _terminate_and_join(process)
                raise IsolatedProcessTimeoutError("The isolated process timed out")
            if process.exitcode != 0:
                raise IsolatedProcessError("The isolated process failed")

            if status != "ok":
                raise IsolatedProcessError("The isolated process failed")
            return payload
        except BaseException:
            if started and process.is_alive():
                await _terminate_and_join(process)
            raise
        finally:
            result_queue.close()
            result_queue.join_thread()


async def _terminate_and_join(process: BaseProcess) -> None:
    process.terminate()
    await asyncio.to_thread(process.join, 0.5)
    if process.is_alive():
        process.kill()
        await asyncio.to_thread(process.join)
