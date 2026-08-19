"""dsh plugin package.

Submodules that need ageval Core (factory, container) must be imported by
name. Package import itself stays Core-free so the in-container worker can
load ``dsh_plugin.trajectory``.
"""

PLUGIN_ID = "dsh"

__all__ = ["PLUGIN_ID"]
