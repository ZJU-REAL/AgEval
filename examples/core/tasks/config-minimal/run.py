"""Example harness module for config-minimal.

Config Core must never import or execute this file during ``ageval lock``.
It exists only so package layout and entrypoint locator validation succeed.
"""


async def run(ctx: object) -> None:
    """Placeholder entrypoint — not invoked by v0.1 Config checkpoint."""
    raise RuntimeError("config-minimal harness is not executable in v0.1")
