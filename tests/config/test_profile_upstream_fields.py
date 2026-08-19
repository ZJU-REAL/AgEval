"""Profile base_url + api_key (env locator) config validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from tests.helpers.lock import lock_with_profiles

from ageval.config.errors import ConfigError
from ageval.config.model import thaw

REPO = Path(__file__).resolve().parents[2]


def _write_pkg(tmp: Path, *, slot_id: str = "glm") -> Path:
    pkg = tmp / "pkg"
    pkg.mkdir()
    (pkg / "run.py").write_text("async def run(ctx):\n    pass\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("def evaluate(i):\n    return {}\n", encoding="utf-8")
    doc = {
        "format": "ageval.task/1",
        "task_id": "profile-upstream",
        "parameters": {},
        "agent_profiles": [{"id": slot_id}],
        "limits": {
            "wall_time_seconds": 60,
            "agent_invocations": 1,
        },
        "artifacts": {"publishable": []},
        "evaluation": {
            "entrypoint": "evaluator:evaluate",
            "inputs": [],
        },
    }
    (pkg / "task.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return pkg


def test_accepts_base_url_and_api_key_locator(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, slot_id="glm")
    locked = lock_with_profiles(
        pkg,
        "profile-upstream",
        {
            "glm": {
                "executor": "openai-http",
                "model": "glm-4.7",
                "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "api_key": "${zhipu_coding_api_key}",
            }
        },
    )
    profiles = thaw(locked.agent_profiles)
    assert profiles[0]["base_url"].startswith("https://")
    assert profiles[0]["api_key"] == "zhipu_coding_api_key"


def test_rejects_secret_like_api_key(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, slot_id="bad")
    with pytest.raises(ConfigError) as ei:
        lock_with_profiles(
            pkg,
            "profile-upstream",
            {
                "bad": {
                    "executor": "openai-http",
                    "model": "glm-4.7",
                    "api_key": "sk-this-is-a-secret-value-not-a-locator",
                }
            },
        )
    assert "api_key" in str(ei.value).lower() or ei.value.error_code == "invalid_schema"


def test_rejects_non_url_base(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, slot_id="bad")
    with pytest.raises(ConfigError):
        lock_with_profiles(
            pkg,
            "profile-upstream",
            {
                "bad": {
                    "executor": "openai-http",
                    "model": "glm-4.7",
                    "base_url": "not-a-url",
                }
            },
        )


def test_expands_base_url_env_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_LITELLM_BASE", "http://127.0.0.1:8010/v1")
    pkg = _write_pkg(tmp_path, slot_id="glm")
    locked = lock_with_profiles(
        pkg,
        "profile-upstream",
        {
            "glm": {
                "executor": "openai-http",
                "model": "glm-4.7",
                "base_url": "${TEST_LITELLM_BASE}",
                "api_key": "${zhipu_coding_api_key}",
            }
        },
    )
    profiles = thaw(locked.agent_profiles)
    assert profiles[0]["base_url"] == "http://127.0.0.1:8010/v1"
    assert profiles[0]["api_key"] == "zhipu_coding_api_key"


def test_rejects_bare_api_key_locator(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, slot_id="glm")
    with pytest.raises(ConfigError, match=r"\$\{ENV_NAME\}"):
        lock_with_profiles(
            pkg,
            "profile-upstream",
            {
                "glm": {
                    "executor": "openai-http",
                    "model": "glm-4.7",
                    "api_key": "zhipu_coding_api_key",
                }
            },
        )


def test_rejects_unset_base_url_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_BASE_URL", raising=False)
    pkg = _write_pkg(tmp_path, slot_id="glm")
    with pytest.raises(ConfigError, match="unset"):
        lock_with_profiles(
            pkg,
            "profile-upstream",
            {
                "glm": {
                    "executor": "openai-http",
                    "model": "glm-4.7",
                    "base_url": "${MISSING_BASE_URL}",
                    "api_key": "${zhipu_coding_api_key}",
                }
            },
        )
