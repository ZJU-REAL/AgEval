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
- Count tag occurrences across all `tags` arrays; keep top 5 tags by count (desc).
- Do not print all records. After writing `aggregates.json`, return exactly `{"status":"completed"}`.
