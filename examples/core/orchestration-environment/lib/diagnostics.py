"""Diagnostic specialist probes and label allowlist (package domain data)."""

from __future__ import annotations

ALLOWED_LABELS = (
    "INSERT_LARGE_DATA",
    "LOCK_CONTENTION",
    "VACUUM",
    "REDUNDANT_INDEX",
    "FETCH_LARGE_DATA",
)

# Per-specialist read-only probes (SQL only — gold not in the string).
SPECIALIST_SQL: dict[str, str] = {
    "INSERT_LARGE_DATA": (
        "SELECT query, calls, total_exec_time, rows FROM pg_stat_statements_sim "
        "ORDER BY rows DESC LIMIT 5"
    ),
    "LOCK_CONTENTION": (
        "SELECT blocked_pid, blocking_pid, wait_event, duration_ms "
        "FROM lock_waits_sim ORDER BY duration_ms DESC"
    ),
    "VACUUM": ("SELECT relname, n_live_tup, n_dead_tup, last_vacuum FROM table_bloat_sim"),
    "REDUNDANT_INDEX": (
        "SELECT indexrelname, idx_scan, idx_tup_read, is_unique FROM index_usage_sim"
    ),
    "FETCH_LARGE_DATA": ("SELECT query, avg_rows, shared_blks_read FROM large_fetch_sim"),
}
