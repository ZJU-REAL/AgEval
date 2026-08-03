"""Redaction and fail-closed secret scan for trajectory evidence."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from typing import Any

# Patterns that indicate secrets / credentials in serialized evidence.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*:\s*)bearer\s+\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|credential)\s*[:=]\s*\S+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)(xox[baprs]-)[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)(postgres(?:ql)?://[^:\s/]+:)[^@\s]+@"),
    re.compile(r"(?i)(mysql://[^:\s/]+:)[^@\s]+@"),
    re.compile(r"(?i)(mongodb(?:\+srv)?://[^:\s/]+:)[^@\s]+@"),
    re.compile(r"(?i)cookie\s*[:=]\s*[^\s;]+"),
    # Host credential path shapes that must not appear in evidence.
    re.compile(r"(?i)/Users/[^/\s]+/\.codex/auth\.json"),
    re.compile(r"(?i)/home/[^/\s]+/\.codex/auth\.json"),
    re.compile(r"(?i)~/?\.codex/auth\.json"),
)

_REDACTED = "[REDACTED:secret]"


class RedactionError(Exception):
    """Raised when residual secret content is found after redaction (fail closed)."""

    def __init__(self, message: str, *, hits: list[str] | None = None) -> None:
        super().__init__(message)
        # Never include the secret values themselves — only class labels.
        self.hits = list(hits or [])


def redact_text(text: str, *, extra_sentinels: Iterable[str] = ()) -> str:
    """Replace known secret shapes and explicit sentinels in a string."""
    out = text
    for s in extra_sentinels:
        if s and s in out:
            out = out.replace(s, _REDACTED)
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


def redact_value(value: Any, *, extra_sentinels: Iterable[str] = ()) -> Any:
    """Deep-redact strings inside JSON-like structures."""
    sent = tuple(s for s in extra_sentinels if s)
    if isinstance(value, str):
        return redact_text(value, extra_sentinels=sent)
    if isinstance(value, Mapping):
        return {str(k): redact_value(v, extra_sentinels=sent) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, extra_sentinels=sent) for v in value]
    if isinstance(value, tuple):
        return [redact_value(v, extra_sentinels=sent) for v in value]
    return value


def scan_for_secrets(
    value: Any,
    *,
    extra_sentinels: Iterable[str] = (),
) -> list[str]:
    """Return class labels of residual secret hits (empty means clean)."""
    hits: list[str] = []
    sent = [s for s in extra_sentinels if s]

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            for s in sent:
                if s in obj:
                    hits.append("sentinel")
            for pat in _SECRET_PATTERNS:
                if pat.search(obj):
                    hits.append("pattern")
            return
        if isinstance(obj, Mapping):
            for v in obj.values():
                _walk(v)
            return
        if isinstance(obj, Sequence) and not isinstance(obj, (bytes, bytearray)):
            for v in obj:
                _walk(v)

    _walk(value)
    return hits


def assert_clean(value: Any, *, extra_sentinels: Iterable[str] = ()) -> None:
    """Fail closed if any residual secret remains."""
    hits = scan_for_secrets(value, extra_sentinels=extra_sentinels)
    if hits:
        raise RedactionError(
            "secret residual after redaction; refusing to seal trajectory",
            hits=sorted(set(hits)),
        )


def redact_and_assert(value: Any, *, extra_sentinels: Iterable[str] = ()) -> Any:
    cleaned = redact_value(value, extra_sentinels=extra_sentinels)
    assert_clean(cleaned, extra_sentinels=extra_sentinels)
    return cleaned


def register_sentinel(bucket: MutableMapping[str, str], name: str, value: str) -> None:
    """Helper for tests: record a sentinel value that must never appear on disk."""
    if value:
        bucket[name] = value
