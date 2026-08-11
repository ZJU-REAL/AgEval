"""nooa external plugin — host SPI executor for package-local agents."""

from __future__ import annotations

from nooa_plugin.factory import PLUGIN_ID, NooaExecutorSPI, build_executor

__all__ = ["PLUGIN_ID", "NooaExecutorSPI", "build_executor"]
