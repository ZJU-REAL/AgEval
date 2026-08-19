"""ageval Core 4 — Attempt-scoped Capability API (v0.4).

Pre-effect authorization for params, scope, agent, environment, workspace,
artifacts, and events. Hard ceilings for agent_invocations / environment_actions
are process-local single-Attempt authority only.
"""

from ageval.capabilities.authority import AttemptCapabilityAuthority
from ageval.capabilities.errors import CapabilityError

__all__ = ["AttemptCapabilityAuthority", "CapabilityError"]
