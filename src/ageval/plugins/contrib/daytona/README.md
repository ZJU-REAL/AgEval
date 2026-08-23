# daytona environment

First-party exclusive-slot winner for `environment: daytona`.

The Attempt runs in a [Daytona](https://www.daytona.io) sandbox built from
an OCI snapshot. Vendor SDK objects, snapshot names, and sandbox ids stay
in this package. Neighbors only call Protocol methods (`upload` / `exec` /
`attach_stdio`).

## Bind

```yaml
environment: daytona
```

This host needs:

- `uv sync --extra daytona`
- `DAYTONA_API_KEY` (or the scoped locator alias)

Floating tags such as `latest` / `lts` / `stable` are rejected. Missing
extra or key: lock/run **skip or fail-closed**. A Hub card is not
evidence that this machine can run Daytona.

Not a Hub install. `ageval plugin install daytona` fail-closes: the id is
reserved.
