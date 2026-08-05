# Terminal workspace task

There are JSONL files in the current working directory (e.g. `records_1.jsonl`, `records_2.jsonl`, ...).

Aggregate all records and write `aggregates.json` in the current working directory with exactly:

```json
{
  "top_5_users_by_amount": {
    "<user>": {"total_amount": <float rounded to 2 decimals>, "total_items": <int>}
  },
  "top_5_tags_by_count": {
    "<tag>": {"count": <int>}
  }
}
```

Rules:
- Sum `amount` and `items` per `user`; keep top 5 users by total_amount (desc).
  Ties: prefer higher total_items, then user name ascending.
- Count tag occurrences across all `tags` arrays; keep top 5 tags by count (desc).
  Ties: tag name ascending.
- Do not invent numbers — read every `records_*.jsonl` file in the cwd.
- Write `aggregates.json` to the current working directory (this file is the task output).
- After the file is written, reply with a short confirmation. Prefer returning the same
  JSON object as in `aggregates.json`, or `{"status":"completed"}` if the file is already correct.
