"""ACP failure detail must reach evidence, not just a bare error kind.

Found via live eval: claude-agent-acp returned error.data.details
("--dangerously-skip-permissions cannot be used with root/sudo…") but the
executor surfaced only ``acp_protocol_error``.
"""

from __future__ import annotations

from ageval.plugins.contrib.acp.executor import AcpExecutor


class _RequestErrorLike(Exception):
    def __init__(self, message: str, data: object) -> None:
        super().__init__(message)
        self.data = data


def test_exc_detail_prefers_request_error_data() -> None:
    exc = _RequestErrorLike(
        "Internal error",
        {"details": "Claude Code process exited with code 1. stderr: root refused"},
    )
    detail = AcpExecutor._exc_detail(exc)
    assert detail is not None
    assert "root refused" in detail


def test_exc_detail_falls_back_to_message_keys_and_str() -> None:
    assert AcpExecutor._exc_detail(_RequestErrorLike("x", {"message": "adapter said no"})) == (
        "adapter said no"
    )
    assert AcpExecutor._exc_detail(RuntimeError("plain failure")) == "plain failure"
    assert AcpExecutor._exc_detail(RuntimeError("")) is None


def test_exc_detail_truncates_long_payloads() -> None:
    exc = _RequestErrorLike("Internal error", {"details": "x" * 1000})
    detail = AcpExecutor._exc_detail(exc)
    assert detail is not None and len(detail) == 300


def test_spi_creates_pointed_home_subdirs(tmp_path) -> None:
    """codex exits 1 when CODEX_HOME points at a missing dir (live-eval find)."""
    from ageval.plugins.contrib.acp import AcpExecutorSPI

    home = tmp_path / "attempt-home"
    home.mkdir()
    AcpExecutorSPI(
        options={"entry": "codex"},
        profile_id="solver",
        model="entry-default",
        home=str(home),
    )
    for sub in (".codex", ".config", ".cache", ".local/state", ".local/share"):
        assert (home / sub).is_dir(), sub
