# local environment

First-party exclusive-slot winner for `environment: local`.

The Attempt uses a real directory tree on this host. In-box paths
(`/attempt/workspace`, `/attempt/home`, `/attempt/evaluation`, artifacts)
map onto those directories. `exec` is a real subprocess; `attach_stdio`
hands ACP a live `Popen` pipe. Gold stays off the Agent mount and is
uploaded only before evaluate.

## Bind

```yaml
environment: local
```

No extra Python package. The process must be able to write the work root.
This is a production kind, not a mock box.

Not a Hub install. `ageval plugin install local` fail-closes: the id is
reserved.
