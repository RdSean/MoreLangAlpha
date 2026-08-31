"""Services for channel linking and gateway orchestration."""

from src.server.services.channels.event_dispatcher import (
    ChannelEventDispatcher,
    PresentationSink,
)

__all__ = ["ChannelEventDispatcher", "PresentationSink"]
