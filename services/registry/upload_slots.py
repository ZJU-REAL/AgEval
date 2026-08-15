"""In-flight upload cap (per process).

Public deploy: workers × this limit is the process-side ceiling. Put the
same number (or smaller) on the reverse proxy so disk / NIC cannot fill.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from services.registry.errors import RegistryAppError

DEFAULT_UPLOAD_SLOTS = 4


def slots_from_env(*, default: int = DEFAULT_UPLOAD_SLOTS) -> int:
    raw = (os.environ.get("BORA_REGISTRY_UPLOAD_SLOTS") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


class UploadSlotPool:
    """Non-blocking semaphore. Exhaustion is 429, not a queue."""

    def __init__(self, limit: int = DEFAULT_UPLOAD_SLOTS) -> None:
        self.limit = max(1, int(limit))
        self._sem = threading.BoundedSemaphore(self.limit)

    def try_acquire(self) -> bool:
        return self._sem.acquire(blocking=False)

    def release(self) -> None:
        self._sem.release()

    @contextmanager
    def hold(self) -> Iterator[None]:
        if not self.try_acquire():
            raise RegistryAppError(
                "too_many_uploads",
                f"in-flight upload limit {self.limit} reached",
                http_status=429,
            )
        try:
            yield
        finally:
            self.release()
