"""
Per-campaign event queues for SSE streaming.

The segmentation pipeline emits progress events via emit().
The API SSE endpoint subscribes by calling register() before the pipeline
starts, then drains the queue with get_queue() until it sees SENTINEL.

Queue lifecycle:
  register(id) → pipeline runs → nodes call emit() → SSE drains → close() → unregister(id)

Design notes:
- One asyncio.Queue per campaign — isolated, no cross-campaign interference.
- maxsize=1000 prevents unbounded memory growth if the SSE consumer falls behind.
- SENTINEL (None) placed by close() tells the consumer the stream is done.
- unregister() is called by the SSE endpoint after it finishes streaming so
  memory is reclaimed even if the browser disconnects mid-stream.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

SENTINEL = None   # placed in queue to signal end-of-stream

_queues: dict[int, asyncio.Queue] = {}


def register(campaign_id: int) -> asyncio.Queue:
    """
    Create and register the event queue for a campaign.
    Must be called before the pipeline starts so no events are lost.
    """
    q: asyncio.Queue[Any] = asyncio.Queue(maxsize=1000)
    _queues[campaign_id] = q
    return q


def unregister(campaign_id: int) -> None:
    """
    Remove the queue after the SSE consumer is done.
    Safe to call even if the campaign was never registered.
    """
    _queues.pop(campaign_id, None)


async def emit(campaign_id: int, event: dict) -> None:
    """
    Push an event to the campaign queue.
    Drops silently if the queue is full or unregistered — never blocks the pipeline.
    """
    q = _queues.get(campaign_id)
    if q is None:
        return
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning(
            f"Campaign {campaign_id}: event queue full, dropping event type={event.get('type','?')}"
        )


async def close(campaign_id: int) -> None:
    """
    Place SENTINEL in the queue to signal stream end.
    The SSE endpoint stops iterating when it dequeues SENTINEL.
    """
    q = _queues.get(campaign_id)
    if q is not None:
        try:
            q.put_nowait(SENTINEL)
        except asyncio.QueueFull:
            pass


def get_queue(campaign_id: int) -> Optional[asyncio.Queue]:
    """Return the queue for a campaign, or None if not registered."""
    return _queues.get(campaign_id)
