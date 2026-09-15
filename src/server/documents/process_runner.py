"""Bounded execution of native document code in spawned child processes."""

from __future__ import annotations

import asyncio
import multiprocessing
import queue
import time
from collections.abc import Callable
from multiprocessing.process import BaseProcess
from typing import Any

from src.server.documents.contracts import DocumentDomainError


class IsolatedProcessError(RuntimeError):
    """A stable error for child startup, crash, or invalid output."""


class IsolatedProcessTimeoutError(IsolatedProcessError):
    """Raised after the child is terminated at its deadline."""


_ISOLATED_FAILURE = "The isolated process failed"

# Long enough for an exception type and the provider's own words, short enough
# that a runaway message cannot become the log line.
_MAX_ERROR_SUMMARY_CHARS = 400


def _summarise(error: BaseException) -> str:
    """A bounded one-line description of what the child died of.

    The child's exception is the only record of why a parser failed — it can be
    a revoked credential, a provider outage, or our own bug — and the child
    prints nothing of its own, so the summary is sent back rather than dropped.
    The parent keeps it out of the job's user-facing message and logs it.
    """
    return f"{type(error).__name__}: {error}".strip()[:_MAX_ERROR_SUMMARY_CHARS]


def _failed_message(detail: object) -> str:
    if isinstance(detail, str) and detail:
        return f"{_ISOLATED_FAILURE}: {detail}"
    return _ISOLATED_FAILURE


def _execute_child(
    result_queue: Any,
    target: Callable[..., object],
    args: tuple[object, ...],
) -> None:
    try:
        result = target(*args)
    except DocumentDomainError as error:
        # A described failure keeps its code and safe message. The class itself
        # is not pickled back: the code is the contract, and the parent rebuilds
        # the error from it so ``_safe_error`` can still report the real reason.
        result_queue.put(("domain_error", (error.code, error.safe_message)))
    except BaseException as error:
        result_queue.put(("error", _summarise(error)))
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
                        raise IsolatedProcessError(_ISOLATED_FAILURE)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await _terminate_and_join(process)
                raise IsolatedProcessTimeoutError("The isolated process timed out")
            await asyncio.to_thread(process.join, remaining)
            if process.is_alive():
                await _terminate_and_join(process)
                raise IsolatedProcessTimeoutError("The isolated process timed out")
            if process.exitcode != 0:
                raise IsolatedProcessError(_ISOLATED_FAILURE)

            if status == "domain_error":
                code, message = payload
                raise DocumentDomainError(message, code=code)
            if status != "ok":
                raise IsolatedProcessError(_failed_message(payload))
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
