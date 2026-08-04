-- Diagnostic tables for package-local multi-role workflow.
-- Do not document gold labels here; gold lives only under evaluation/.

CREATE TABLE IF NOT EXISTS pg_stat_statements_sim (
  query text PRIMARY KEY,
  calls bigint,
  total_exec_time double precision,
  rows bigint
);

CREATE TABLE IF NOT EXISTS lock_waits_sim (
  blocked_pid int,
  blocking_pid int,
  wait_event text,
  duration_ms int
);

CREATE TABLE IF NOT EXISTS table_bloat_sim (
  relname text PRIMARY KEY,
  n_live_tup bigint,
  n_dead_tup bigint,
  last_vacuum text
);

CREATE TABLE IF NOT EXISTS index_usage_sim (
  indexrelname text PRIMARY KEY,
  idx_scan bigint,
  idx_tup_read bigint,
  is_unique boolean
);

CREATE TABLE IF NOT EXISTS large_fetch_sim (
  query text PRIMARY KEY,
  avg_rows bigint,
  shared_blks_read bigint
);

TRUNCATE pg_stat_statements_sim, lock_waits_sim, table_bloat_sim, index_usage_sim, large_fetch_sim;

INSERT INTO pg_stat_statements_sim(query, calls, total_exec_time, rows) VALUES
  ('INSERT INTO events SELECT * FROM bulk_source', 50000, 980000.0, 50000000),
  ('SELECT id FROM tiny', 10, 1.0, 10);

INSERT INTO lock_waits_sim(blocked_pid, blocking_pid, wait_event, duration_ms) VALUES
  (101, 100, 'Lock', 45000),
  (102, 100, 'Lock', 30000);

INSERT INTO table_bloat_sim(relname, n_live_tup, n_dead_tup, last_vacuum) VALUES
  ('orders', 1000, 800000, 'never'),
  ('users', 500, 2, '2026-01-01');

INSERT INTO index_usage_sim(indexrelname, idx_scan, idx_tup_read, is_unique) VALUES
  ('orders_note_idx', 0, 0, false),
  ('orders_pkey', 10000, 10000, true);

INSERT INTO large_fetch_sim(query, avg_rows, shared_blks_read) VALUES
  ('SELECT * FROM archive', 5, 100),
  ('SELECT id FROM archive LIMIT 1', 1, 2);
