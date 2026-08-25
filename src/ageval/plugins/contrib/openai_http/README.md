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

No plugin `options` are consumed. Role profile fields only.

| Name | Default | Purpose |
| --- | --- | --- |
| `model` | `gpt-4.1-mini` | Chat Completions model id the endpoint accepts. |
| `base_url` | unset (executor default `https://api.openai.com/v1`) | `${ENV_NAME}` (lock stores the locator) or a literal `http(s)` URL. Host `AGEVAL_OPENAI_BASE_URL` is the fallback when the field is omitted. |
| `api_key` | `OPENAI_API_KEY` | Env **locator name**, not the secret. Empty key is allowed only when `base_url` is loopback. |

## Bind

```yaml
executor: openai-http
model: gpt-4.1-mini          # or another id the endpoint accepts
base_url: ${AGEVAL_OPENAI_BASE_URL}   # or a literal http(s) URL; omit for default
api_key: ${OPENAI_API_KEY}            # env locator, not the secret
```

Native `tools=` is posted when the session has a catalog. Responses may
include `tool_calls` and reasoning `thought` events for the trajectory.
The raw HTTP body stays under `backend_raw`.

`RunTerminal.completed` is not PASS. PASS still comes from the independent
evaluator.

Not a Hub install. `ageval plugin install openai-http` fail-closes: the
id is reserved.
