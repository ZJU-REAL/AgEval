"""Local read-only Database results viewer (HTTP + Vite SPA).

Serves Jobs → Tasks → Trial over suite-runs. Not ageval Core.
Does not require Registry, Postgres, or OAuth.
"""

from __future__ import annotations

__all__ = ["serve_viewer"]


def serve_viewer(*args, **kwargs):  # noqa: ANN002, ANN003
    from ageval.viewer.server import serve_viewer as _serve

    return _serve(*args, **kwargs)
