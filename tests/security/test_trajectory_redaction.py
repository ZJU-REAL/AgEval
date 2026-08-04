"""Trajectory redaction: patterns + sentinels never land on disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.evidence.redaction import (
    RedactionError,
    assert_clean,
    redact_and_assert,
    redact_text,
    scan_for_secrets,
)
from bora.evidence.store import AttemptEvidenceStore


def test_redact_bearer_and_sk() -> None:
    raw = "Authorization: Bearer sk-abc123456789 token=secret"
    out = redact_text(raw)
    assert "sk-abc" not in out
    assert "Bearer sk-" not in out
    assert "REDACTED" in out


def test_redact_dsn_password() -> None:
    raw = "postgres://user:s3cretpass@localhost:5432/db"
    out = redact_text(raw)
    assert "s3cretpass" not in out


def test_sentinel_scan() -> None:
    sentinel = "RAND_SENTINEL_9f3a2b"
    hits = scan_for_secrets({"msg": f"x {sentinel} y"}, extra_sentinels=[sentinel])
    assert "sentinel" in hits


def test_assert_clean_fail_closed() -> None:
    with pytest.raises(RedactionError):
        assert_clean("Authorization: Bearer supersecretvaluehere")


def test_redact_and_assert_nested() -> None:
    cleaned = redact_and_assert(
        {"a": {"b": "Authorization: Bearer abcdefghijklmnop"}},
    )
    assert "abcdefghijklmnop" not in str(cleaned)


def test_store_request_redacts_sentinel(tmp_path: Path) -> None:
    sentinel = "ENV_SECRET_VALUE_TEST_991"
    store = AttemptEvidenceStore(
        root=tmp_path / "r",
        attempt_id="a",
        sentinels=[sentinel],
    )
    h = store.begin_invocation(profile_id="p", executor_kind="codex", model="m")
    # write_request redacts; residual would raise — after redaction sentinel is gone
    h.write_request(
        {
            "messages": [{"role": "user", "content": f"token is {sentinel}"}],
            "env_hint": f"x={sentinel}",
        }
    )
    body = (h.directory / "request.json").read_text(encoding="utf-8")
    assert sentinel not in body
    assert "REDACTED" in body
