"""asyncio streams over a box's stdio transport.

A protocol client (ACP today) needs a reader/writer pair, and the pipe it gets
came from ``environment.attach_stdio``. Adapting one to the other is transport
plumbing, so it lives next to the transport protocol rather than in the plugin
that happens to speak JSON-RPC.
"""

from __future__ import annotations

import asyncio
from typing import IO, Any, cast

from ageval.environments.protocol import EnvironmentFailure, StdioTransport

# ACP payloads (file diffs, tool output) exceed asyncio's 64 KiB line default.
STREAM_LIMIT = 8 * 1024 * 1024


async def open_streams(pipe: StdioTransport) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Wrap an attached process's pipes as asyncio streams on the running loop."""
    loop = asyncio.get_running_loop()
    read_end = _byte_stream(pipe.stdout, name="stdout")
    write_end = _byte_stream(pipe.stdin, name="stdin")

    reader = asyncio.StreamReader(limit=STREAM_LIMIT)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), read_end)

    transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, write_end)
    writer = asyncio.StreamWriter(transport, cast(Any, protocol), None, loop)
    return reader, writer


def _byte_stream(end: object, *, name: str) -> IO[bytes]:
    if end is None or not hasattr(end, "fileno"):
        raise EnvironmentFailure(
            "environment_attach_invalid",
            f"attached process exposes no {name} pipe",
        )
    return cast("IO[bytes]", end)
