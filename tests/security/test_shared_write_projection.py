"""shared_write path validation (lock-time)."""

from __future__ import annotations

import pytest

from bora.config.errors import ConfigError
from bora.provider.isolation import parse_logical_topology


def test_shared_write_relative_ok() -> None:
    topo = parse_logical_topology(
        {
            "network": "none",
            "agent_isolation": {
                "mode": "shared-container",
                "groups": [
                    {
                        "id": "g",
                        "actors": [{"id": "a", "profiles": ["p"]}],
                        "shared_write": ["workspace/team", "workspace/out"],
                    }
                ],
            },
        },
        profile_ids={"p"},
    )
    assert topo is not None
    assert topo.actors[0].shared_write == ("workspace/team", "workspace/out")


def test_shared_write_symlink_escape_style_rejected() -> None:
    with pytest.raises(ConfigError):
        parse_logical_topology(
            {
                "network": "none",
                "agent_isolation": {
                    "mode": "shared-container",
                    "groups": [
                        {
                            "id": "g",
                            "actors": [{"id": "a", "profiles": ["p"]}],
                            "shared_write": ["foo/../../etc"],
                        }
                    ],
                },
            },
            profile_ids={"p"},
        )
