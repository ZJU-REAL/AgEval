"""Length-capped upload spool and on-disk multipart split."""

from __future__ import annotations

import json
import mmap
import re
import secrets
from pathlib import Path
from typing import Any, BinaryIO

from services.registry.errors import RegistryAppError


def spool_body(
    body: BinaryIO,
    *,
    length: int,
    max_bytes: int,
    dest_dir: Path,
) -> Path:
    """Write at most *max_bytes* from *body* into a temp file. Hash is not required."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"upload-{secrets.token_hex(8)}.spool"
    remaining = length
    written = 0
    try:
        with dest.open("wb") as out:
            while remaining > 0:
                block = body.read(min(64 * 1024, remaining))
                if not block:
                    break
                written += len(block)
                if written > max_bytes:
                    raise RegistryAppError(
                        "payload_too_large",
                        f"max {max_bytes} bytes",
                        http_status=413,
                    )
                out.write(block)
                remaining -= len(block)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if written <= 0:
        dest.unlink(missing_ok=True)
        raise RegistryAppError(
            "payload_too_large",
            f"max {max_bytes} bytes",
            http_status=413,
        )
    return dest


def extract_multipart_archive(
    spool: Path,
    content_type: str,
    dest_dir: Path,
) -> tuple[dict[str, Any], Path]:
    """Split a multipart spool into metadata JSON and an archive file."""
    match = re.search(r"boundary=([^;]+)", content_type)
    if not match:
        raise ValueError("missing multipart boundary")
    boundary = match.group(1).strip().encode()
    marker = b"--" + boundary
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / f"archive-{secrets.token_hex(8)}.bin"
    meta: dict[str, Any] | None = None
    found_archive = False
    with spool.open("rb") as fh:
        mapped = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            positions = _marker_positions(mapped, marker)
            for index, start in enumerate(positions):
                payload_at = start + len(marker)
                if payload_at + 2 <= len(mapped) and mapped[payload_at : payload_at + 2] == b"--":
                    continue
                if payload_at + 2 <= len(mapped) and mapped[payload_at : payload_at + 2] == b"\r\n":
                    payload_at += 2
                header_end = mapped.find(b"\r\n\r\n", payload_at)
                if header_end < 0:
                    continue
                headers = mapped[payload_at:header_end].decode("utf-8", errors="replace")
                name_m = re.search(r'name="([^"]+)"', headers)
                if not name_m:
                    continue
                data_start = header_end + 4
                data_end = positions[index + 1] if index + 1 < len(positions) else len(mapped)
                # Strip the CRLF that precedes the next boundary.
                if data_end >= 2 and mapped[data_end - 2 : data_end] == b"\r\n":
                    data_end -= 2
                name = name_m.group(1)
                if name == "metadata":
                    raw = bytes(mapped[data_start:data_end])
                    meta = json.loads(raw.decode("utf-8"))
                elif name == "archive":
                    _copy_span(mapped, data_start, data_end, archive_path)
                    found_archive = True
        finally:
            mapped.close()
    if meta is None or not found_archive:
        archive_path.unlink(missing_ok=True)
        raise ValueError("metadata and archive parts required")
    if not isinstance(meta, dict):
        archive_path.unlink(missing_ok=True)
        raise ValueError("metadata must be a JSON object")
    return meta, archive_path


def _marker_positions(mapped: mmap.mmap, marker: bytes) -> list[int]:
    found: list[int] = []
    cursor = 0
    while True:
        at = mapped.find(marker, cursor)
        if at < 0:
            return found
        found.append(at)
        cursor = at + len(marker)


def _copy_span(mapped: mmap.mmap, start: int, end: int, dest: Path) -> None:
    with dest.open("wb") as out:
        cursor = start
        while cursor < end:
            block = mapped[cursor : min(cursor + 1024 * 1024, end)]
            out.write(block)
            cursor += len(block)
