# openai-http executor

First-party exclusive-slot winner for `executor: openai-http`.

Thin HTTP Chat backend. It does not own Run identity, PASS, or host
credentials beyond a **scoped env locator** for the API key. No Attempt
box is required; this executor does not inject `environment`.

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
| `options.reasoning_effort` | omit | Optional OpenAI-shaped Chat Completions `reasoning_effort`. Empty / omit = do not send. Non-string values are rejected. |
| `options.extra_body` | omit | Optional mapping merged as-is into the Chat Completions JSON body (after `reasoning_effort`). Vendor-native keys (OpenRouter `reasoning` / `provider`, …). Omit / empty = do not merge. Non-mapping values are rejected. Rejects `model` / `api_key` / `messages` / `tools`. Conflicting keys: extra_body wins. |
| `model` | `gpt-4.1-mini` | Chat Completions model id the endpoint accepts (`openai/…`, `deepseek/…`, or any id the `base_url` gateway accepts). |
| `base_url` | unset (executor default `https://api.openai.com/v1`) | `${ENV_NAME}` (lock stores the locator) or a literal `http(s)` URL. Host `AGEVAL_OPENAI_BASE_URL` is the fallback when the field is omitted. Point at OpenRouter, DashScope, a local gateway, etc. |
| `api_key` | `OPENAI_API_KEY` | Env **locator name**, not the secret. Empty key is allowed only when `base_url` host is `127.0.0.1` / `localhost` / `::1`. |

## Bind

```yaml
executor: openai-http
model: deepseek/deepseek-v4-flash-0731
base_url: https://openrouter.ai/api/v1
api_key: ${openrouter_api_key}
options:
  extra_body:
    provider:
      allow_fallbacks: false
```

Native `tools=` is posted when the session has a catalog. Responses may
include `tool_calls` and reasoning `thought` events for the trajectory.
The raw HTTP body stays under `backend_raw`.

`RunTerminal.completed` is not PASS. PASS still comes from the independent
evaluator.

Not a Hub install. `ageval plugin install openai-http` is rejected: the
id is reserved.
