"""Viewer trial preview / enumeration caps and text suffixes."""

from __future__ import annotations

# Preview / enumeration caps (operator-facing local tool, not bulk export).
MAX_FILE_BYTES = 512 * 1024
MAX_TREE_ENTRIES = 800
MAX_TRAJECTORY_STEPS = 2_000
MAX_JSONL_LINE = 256 * 1024

TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".sh",
    ".log",
    ".csv",
    ".tsv",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".ini",
    ".cfg",
    ".conf",
}
