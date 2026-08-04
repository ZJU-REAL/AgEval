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
uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance \
  --set '/parameters/active_profile="opencode-acp"'
```

Harness does not branch on entry names; switch only via `--set` / profile id.
