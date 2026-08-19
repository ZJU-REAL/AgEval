"""L1 Provider error types."""

from __future__ import annotations

from ageval.provider.errors import ProviderError


class ProviderL1Error(ProviderError):
    """L1-specific errors with stable kinds from Spec 07."""
