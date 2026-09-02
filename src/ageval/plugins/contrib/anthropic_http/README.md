# anthropic-http executor

First-party exclusive-slot winner for `executor: anthropic-http`.

Thin Anthropic **Messages** HTTP backend. It does not own Run identity,
PASS, or host credentials beyond a **scoped env locator** for the API
key. No Attempt box is required; this executor does not inject
`environment`.

This is not a dialect of `openai-http`. Chat Completions (including
Anthropic's official OpenAI-compatible layer) stay on `openai-http`.
Messages-only endpoints and native `tool_use` / `thinking` use this
kind.

SDK `tools=` / `messages=` remain OpenAI-shaped. Translation to
`/messages` + `tool_use` happens in this executor.

## Capabilities

| | Value |
| --- | --- |
| export | exclusive `executor` |
| inject | — (no box) |
| chain | — |
| bake | — |

## Parameters

`options` merge: profile `options` then this plugin's `extensions` row (last wins).

| Name | Default | Purpose |
| --- | --- | --- |
| `options.max_tokens` | `4096` | Required Messages `max_tokens`. Positive int. Non-int values are rejected. |
| `options.anthropic_version` | `2023-06-01` | `anthropic-version` request header. Non-string values are rejected. |
| `options.extra_body` | omit | Optional mapping merged as-is into the Messages JSON (after first-class fields). Vendor keys such as `thinking`. Omit / empty = do not merge. Non-mapping values are rejected. Rejects `model` / `api_key` / `messages` / `tools` / `system` / `max_tokens`. Conflicting keys: extra_body wins. |
| `model` | `claude-sonnet-4-6` | Model id the Messages endpoint accepts. Builtin agent card has no default; pass `--model` on the run. |
| `base_url` | unset (executor default `https://api.anthropic.com/v1`) | `${ENV_NAME}` (lock stores the locator) or a literal `http(s)` URL. Host `AGEVAL_ANTHROPIC_BASE_URL` is the fallback when the field is omitted. |
| `api_key` | `ANTHROPIC_API_KEY` | Env **locator name**, not the secret. Empty key is allowed only when `base_url` host is `127.0.0.1` / `localhost` / `::1`. |

## Bind

```yaml
executor: anthropic-http
model: claude-sonnet-4-6
base_url: https://api.anthropic.com/v1
api_key: ${ANTHROPIC_API_KEY}
options:
  extra_body:
    thinking:
      type: enabled
      budget_tokens: 2000
```

Native `tools=` from the session catalog is posted as Anthropic
`tools`. Responses may include `tool_use` (mapped to `AgentResult.tool_calls`)
and `thinking` (thought events). The raw HTTP body stays under
`backend_raw`.

`RunTerminal.completed` is not PASS. PASS still comes from the independent
evaluator.

Not a Hub install. `ageval plugin install anthropic-http` is rejected: the
id is reserved.
