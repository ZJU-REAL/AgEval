"""Environment Protocol and capability vocabulary (no vendor implementations)."""

from ageval.environments.protocol import (
    ARTIFACTS_PATH,
    CAPABILITY_NAMES,
    EVALUATION_PATH,
    HOME_PATH,
    WORKSPACE_PATH,
    EnvironmentCapabilities,
    EnvironmentFailure,
    EnvironmentProvider,
    ExecResult,
    Placement,
    StdioTransport,
)

__all__ = [
    "ARTIFACTS_PATH",
    "CAPABILITY_NAMES",
    "EVALUATION_PATH",
    "HOME_PATH",
    "WORKSPACE_PATH",
    "EnvironmentCapabilities",
    "EnvironmentFailure",
    "EnvironmentProvider",
    "ExecResult",
    "Placement",
    "StdioTransport",
]
