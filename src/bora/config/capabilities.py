"""Declaration-only capability catalog.

Config asks "is this declaration recognizable?" — never "is the adapter ready?".
Positive answers do not constitute runtime implementation evidence.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CapabilityCatalog(Protocol):
    """Read-only catalog used during Config validation."""

    def supports_format(self, format_id: str) -> bool:
        """Return True if the package format id is known to Config."""
        ...

    def supports_harness_runtime(self, runtime: str) -> bool:
        """Return True if the harness runtime declaration is known."""
        ...

    def supports_provider_kind(self, kind: str) -> bool:
        """Return True if the provider kind declaration is known."""
        ...

    def supports_executor_kind(self, kind: str) -> bool:
        """Return True if the agent executor kind declaration is known."""
        ...

    def supports_environment_kind(self, kind: str) -> bool:
        """Return True if the environment kind declaration is known."""
        ...

    def supports_evaluation_output_format(self, fmt: str) -> bool:
        """Return True if the evaluation output format is known."""
        ...


class DeclarationCapabilityCatalog:
    """v0.1 catalog: recognizes declared kinds without claiming runtime readiness.

    These sets are intentionally broader than what is *implemented* today so
    that legitimate future packages can still lock. Recognition ≠ runnable.
    """

    # Formats Config understands as document schemas.
    FORMATS: frozenset[str] = frozenset({"bora.task/1"})

    HARNESS_RUNTIMES: frozenset[str] = frozenset({"python"})
    PROVIDER_KINDS: frozenset[str] = frozenset({"local", "docker"})
    # Kept for introspection / tests; runtime answer is known_executor_kinds().
    EXECUTOR_KINDS: frozenset[str] = frozenset(
        {
            "Official/acp",
            "Official/mock",
            "Official/openai-http",
        }
    )
    ENVIRONMENT_KINDS: frozenset[str] = frozenset(
        {"none", "multi-service", "single-service", "local-process"}
    )
    EVALUATION_OUTPUT_FORMATS: frozenset[str] = frozenset({"json"})

    def supports_format(self, format_id: str) -> bool:
        return format_id in self.FORMATS

    def supports_harness_runtime(self, runtime: str) -> bool:
        return runtime in self.HARNESS_RUNTIMES

    def supports_provider_kind(self, kind: str) -> bool:
        return kind in self.PROVIDER_KINDS

    def supports_executor_kind(self, kind: str) -> bool:
        from bora.adapters.executor_inventory import known_executor_kinds

        return kind in known_executor_kinds()

    def supports_environment_kind(self, kind: str) -> bool:
        return kind in self.ENVIRONMENT_KINDS

    def supports_evaluation_output_format(self, fmt: str) -> bool:
        return fmt in self.EVALUATION_OUTPUT_FORMATS
