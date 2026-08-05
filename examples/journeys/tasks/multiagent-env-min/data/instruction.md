# Multiagent database diagnostic (v1 multiagentbench / database-52 class)

Five specialist roles independently inspect Attempt-local PostgreSQL diagnostics
and return a label from the allowed set:

- `INSERT_LARGE_DATA`
- `LOCK_CONTENTION`
- `VACUUM`
- `REDUNDANT_INDEX`
- `FETCH_LARGE_DATA`

A planner may request at most one follow-up SQL query after reading specialist
findings. A reducer must return **exactly three unique** labels supported by the
diagnostic evidence.

**Rules**

- Use only the provided `db_query` tool (read-only SELECT) to inspect the database.
- Do **not** invent metrics that are not present in tool results.
- Do **not** treat the harness prompt as containing the answer labels.
- Final reducer output must be JSON:
  `{"predicted_labels": ["L1","L2","L3"], "supporting_specialists": ["..."]}`
