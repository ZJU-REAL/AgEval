"""Local read-only Database viewer (HTTP + static SPA).

Not BORA Core. Does not require Registry, Postgres, or OAuth.
"""

from __future__ import annotations

__all__ = ["serve_viewer"]


def serve_viewer(*args, **kwargs):  # noqa: ANN002, ANN003
    from bora.viewer.server import serve_viewer as _serve

    return _serve(*args, **kwargs)
