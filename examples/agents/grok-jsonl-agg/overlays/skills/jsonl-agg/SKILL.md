---
name: jsonl-agg
description: Aggregate records_*.jsonl in the workspace into aggregates.json
---

# jsonl-agg

Read every `records_*.jsonl` file in the current working directory. Do not
invent numbers. Write `aggregates.json` in the cwd with exactly:

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

- Sum `amount` and `items` per `user`. Keep top 5 users by `total_amount`
  descending. Ties: higher `total_items`, then user name ascending.
- Count tag occurrences across all `tags` arrays. Keep top 5 tags by count
  descending. Ties: tag name ascending.
- After the file is written, reply with the same JSON object or
  `{"status":"completed"}`.
