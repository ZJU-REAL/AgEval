"""Shared CLI child-env projection."""

from __future__ import annotations

from bora.adapters.child_env import cli_credential_available, project_cli_child_env


def test_allowlist_drops_unrelated_secrets() -> None:
    host = {
        "PATH": "/bin",
        "HOME": "/home/u",
        "ZAI_API_KEY": "k-pi",
        "UNRELATED_SECRET": "nope",
    }
    env = project_cli_child_env("pi", host_environ=host)
    assert env["ZAI_API_KEY"] == "k-pi"
    assert "UNRELATED_SECRET" not in env
    assert env.get("TERM") == "dumb"


def test_base_url_projects_to_provider_env_names() -> None:
    host = {"PATH": "/bin", "HOME": "/h"}
    env = project_cli_child_env(
        "claude-code",
        base_url="https://open.bigmodel.cn/api/anthropic",
        host_environ=host,
    )
    assert env["ANTHROPIC_BASE_URL"] == "https://open.bigmodel.cn/api/anthropic"
    assert env["OPENAI_BASE_URL"] == "https://open.bigmodel.cn/api/anthropic"


def test_api_key_locator_aliases_per_kind() -> None:
    host = {
        "PATH": "/bin",
        "HOME": "/h",
        "glm_coding_api_key": "secret-glm",
    }
    pi_env = project_cli_child_env(
        "pi", api_key_env="glm_coding_api_key", host_environ=host
    )
    assert pi_env["glm_coding_api_key"] == "secret-glm"
    assert pi_env["ZAI_API_KEY"] == "secret-glm"
    assert pi_env["ZAI_CODING_CN_API_KEY"] == "secret-glm"
    assert pi_env["ANTHROPIC_AUTH_TOKEN"] == "secret-glm"
    assert pi_env["OPENCODE_API_KEY"] == "secret-glm"


    claude_env = project_cli_child_env(
        "claude-code", api_key_env="glm_coding_api_key", host_environ=host
    )
    assert claude_env["ANTHROPIC_API_KEY"] == "secret-glm"
    assert claude_env["ANTHROPIC_AUTH_TOKEN"] == "secret-glm"
    assert "ZAI_API_KEY" not in claude_env  # not in claude alias set via api_key


def test_zhipu_alias_promotes_to_zai_when_unset() -> None:
    host = {"PATH": "/bin", "HOME": "/h", "ZHIPU_API_KEY": "z"}
    env = project_cli_child_env("pi", host_environ=host)
    assert env["ZAI_API_KEY"] == "z"
    assert env["ZHIPU_API_KEY"] == "z"  # also in pi credential allowlist


def test_credential_available() -> None:
    host = {"PATH": "/bin", "HOME": "/h", "OPENAI_API_KEY": "o"}
    assert cli_credential_available("opencode", host_environ=host)
    assert not cli_credential_available("claude-code", host_environ=host)
    host2 = {**host, "MY_KEY": "x"}
    assert cli_credential_available(
        "claude-code", api_key_env="MY_KEY", host_environ=host2
    )


def test_acp_entry_credential_allowlist_projection() -> None:
    """ACP entries share project_cli_child_env via entry_id kind mapping."""
    host = {
        "PATH": "/bin",
        "HOME": "/h",
        "ZHIPU_API_KEY": "z",
        "UNRELATED_SECRET": "nope",
    }
    env = project_cli_child_env("opencode", host_environ=host)
    assert env.get("ZHIPU_API_KEY") == "z"
    assert "UNRELATED_SECRET" not in env
