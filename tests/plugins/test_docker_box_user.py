"""docker environment_options.user — default Attempt uid, optional root."""

from __future__ import annotations

from pathlib import Path

import pytest

from ageval.environments.protocol import BoxSpec, EnvironmentFailure
from ageval.plugins.contrib.docker.host import ATTEMPT_GID, ATTEMPT_UID, DockerHost, _box_user


def test_box_user_default_is_attempt_uid() -> None:
    assert _box_user(None) == f"{ATTEMPT_UID}:{ATTEMPT_GID}"
    assert _box_user("") == f"{ATTEMPT_UID}:{ATTEMPT_GID}"


@pytest.mark.parametrize("raw", ["root", "ROOT", "0", "0:0"])
def test_box_user_root_aliases(raw: str) -> None:
    assert _box_user(raw) == "0:0"


def test_box_user_numeric() -> None:
    assert _box_user("10001") == "10001:10001"
    assert _box_user("10001:10002") == "10001:10002"


def test_box_user_rejects_garbage() -> None:
    with pytest.raises(EnvironmentFailure, match="uid:gid"):
        _box_user("sudo")
    with pytest.raises(EnvironmentFailure, match="uid:gid"):
        _box_user(True)


def test_host_placement_uses_root_option(tmp_path: Path) -> None:
    spec = BoxSpec(attempt_root=tmp_path / "box", task_root=tmp_path, repo_root=tmp_path)
    host = DockerHost(spec=spec, options={"user": "root"})
    host._container = "ageval-test"
    host._started = True
    assert host.placement().user == "0:0"
    default = DockerHost(spec=spec, options={})
    default._container = "ageval-test"
    default._started = True
    assert default.placement().user == f"{ATTEMPT_UID}:{ATTEMPT_GID}"
