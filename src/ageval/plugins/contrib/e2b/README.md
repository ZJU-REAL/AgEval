# e2b environment

First-party exclusive-slot winner for `environment: e2b`.

The Attempt runs in an [E2B](https://e2b.dev) cloud sandbox built from the
task recipe. Vendor SDK objects stay in this package. Neighbors only call
Protocol methods (`upload` / `exec` / `attach_stdio`).

## Bind

```yaml
environment: e2b
```

This host needs:

- `uv sync --extra e2b`
- an E2B API key in the scoped credential locator

Missing extra or key: lock/run **skip or fail-closed**. Do not treat a
Hub catalog card as “this machine can run e2b”.

Not a Hub install. `ageval plugin install e2b` fail-closes: the id is
reserved.
