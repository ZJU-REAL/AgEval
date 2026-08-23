# openai-http executor

First-party exclusive-slot winner for `executor: openai-http`.

Thin HTTP Chat backend. It does not own Run identity, PASS, or host
credentials beyond a **scoped env locator** for the API key. No Attempt
box is required; this executor does not inject `environment`.

## Bind

```yaml
executor: openai-http
model: gpt-4.1-mini          # or another id the endpoint accepts
base_url: https://api.openai.com/v1   # optional; this is the default
api_key: OPENAI_API_KEY      # env *name*, not the secret
```

Native `tools=` is posted when the session has a catalog. Responses may
include `tool_calls` and reasoning `thought` events for the trajectory.
The raw HTTP body stays under `backend_raw`.

`RunTerminal.completed` is not PASS. PASS still comes from the independent
evaluator.

Not a Hub install. `ageval plugin install openai-http` fail-closes: the
id is reserved.
