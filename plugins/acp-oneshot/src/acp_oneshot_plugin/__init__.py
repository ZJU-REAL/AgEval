"""acp-oneshot plugin package.

Submodules that need ageval Core (factory, container) must be imported by
name. Package import itself stays Core-free so the in-box worker can load
``acp_oneshot_plugin.trajectory``.
"""

PLUGIN_ID = "acp-oneshot"

__all__ = ["PLUGIN_ID"]
