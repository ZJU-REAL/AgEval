"""Shared Config check helpers."""

from __future__ import annotations

import pytest

from ageval.config.checks import reject_env_interpolation, require_agent_profiles_list
from ageval.config.errors import ConfigError


def test_reject_env_interpolation() -> None:
    with pytest.raises(ConfigError, match="interpolation"):
        reject_env_interpolation("x: ${HOME}", what="task.yaml", location="task.yaml")
    reject_env_interpolation("x: 1", what="task.yaml", location="task.yaml")


def test_require_agent_profiles_list() -> None:
    assert require_agent_profiles_list([]) == []
    with pytest.raises(ConfigError, match="agent_profiles must be a list"):
        require_agent_profiles_list({"id": "x"})
