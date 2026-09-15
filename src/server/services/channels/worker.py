"""Standalone channel gateway worker entrypoint.

This module intentionally does not import the FastAPI application or its
lifespan. PostgreSQL leases are the source of truth when multiple workers run.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid

from src.config.settings import get_channel_gateway_config
from src.server.channels.adapters.wechat_ilink import WeChatILinkAdapter
from src.server.channels.agent_adapters.langalpha_flash import LangAlphaFlashAdapter
from src.server.database.pool import get_or_create_pool
from src.server.services.channels.gateway_runner import GatewayRunner

logger = logging.getLogger(__name__)


async def run_worker(*, runner: GatewayRunner | None = None) -> None:
    pool = get_or_create_pool()
    await pool.open()
    owns_runner = runner is None
    if runner is None:
        config = get_channel_gateway_config()
        runner = GatewayRunner(
            channel_adapters={
                "wechat": WeChatILinkAdapter(
                    max_text_length=config.max_ilink_text_length
                )
            },
            # Bounded by the deployment's turn budget rather than the adapter's
            # own default: a channel turn runs a real agent, which can think,
            # compact, and call tools for minutes.
            agent_adapter=LangAlphaFlashAdapter(
                timeout=config.agent_turn_timeout_seconds
            ),
            worker_id=f"channel-worker-{uuid.uuid4()}",
        )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    async def tick(kind):
        while not stop_event.is_set():
            try:
                await kind()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("channel gateway tick failed", exc_info=True)
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=get_channel_gateway_config().worker_poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    tasks = [
        asyncio.create_task(tick(runner.poll_bindings_once), name="channel-poll"),
        asyncio.create_task(tick(runner.process_inbound_once), name="channel-inbound"),
        asyncio.create_task(tick(runner.deliver_once), name="channel-delivery"),
    ]
    try:
        await stop_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if runner is not None and hasattr(runner, "stop"):
            await runner.stop()
        if owns_runner:
            logger.info("channel gateway worker stopped")
        await pool.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
