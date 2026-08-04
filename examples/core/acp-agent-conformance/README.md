# ACP agent conformance (Spec 19)

Public host smoke for unified `executor: acp` + `options.entry`.

## Profiles

| profile id | entry |
| --- | --- |
| `opencode-acp` | opencode (Mode 2) |
| `codex-acp` | codex (Mode 1) |
| `claude-acp` | claude-code (Mode 1) |
| `pi-acp` | pi (Mode 1) |
| `grok-build-acp` | grok-build (Mode 3) |

## Commands

```bash
# Default multi-turn (3 invokes) — good for trajectory review
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance \
  --set '/parameters/active_profile="opencode-acp"'

# Other entries (same harness; profile-only switch)
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance \
  --set '/parameters/active_profile="codex-acp"'
```

Harness does not branch on entry names; switch only via `--set` / profile id.

## Trajectory (turn-level)

Each successful invoke writes:

```text
$logs/agent/invocations/<nnnn>-<invocation-id>/trajectory.jsonl
```

- **One invoke = one turn unit** (merged assistant/thought text, not stream chunks).
- Multi-turn: three `invocations/` dirs; often share one ACP `session_id`; `turn_index` is 1..N.
- See design [05 §8.9.4a](../../../docs/design/05-runtime-core.md#894a-trajectoryjsonlturn-级训练默认).
