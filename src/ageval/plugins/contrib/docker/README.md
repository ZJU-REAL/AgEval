# docker environment

First-party exclusive-slot winner for `environment: docker`.

The Attempt runs in a container built from the task's own recipe (plus
plugin `image_layers` when declared). The official Attempt image bakes
coding-agent ACP entries at **build** time; invoke does not `npm i`.
Container id, `docker exec -u/-w`, and UID/GID stay in this package.
ACP / `run.py` / Core never see `container_id`.

## Capabilities

| | Value |
| --- | --- |
| export | exclusive `environment` |
| capabilities | `exec`, `upload`, `download`, `attach_stdio`, `uid_gid`, `path_views`, `compose`: yes |
| inject | — |

`attach_stdio` is `docker exec -i`. Compose sidecars join the Attempt network by service name.

## Parameters

Job knobs are `environment_options` (not `extensions[].options`).

| Name | Default | Purpose |
| --- | --- | --- |
| `environment_options.image` | unset | Existing image tag; skip local build. Alias: `docker_image`. |
| `environment_options.platform` | this host | `docker` platform (e.g. `linux/arm64`). |
| `environment_options.network` | `bridge` | Attempt container network. A task compose file overrides this to `{project}_default`. |
| `environment_options.user` | `10001:10001` | `docker run --user` and the same identity for `exec` / `attach_stdio`. `root` / `0` / `0:0` → root. Other values must be `uid` or `uid:gid`. Unknown strings are rejected. Default still has `no-new-privileges`. |

## Bind

```yaml
environment: docker
```

The host needs a working Docker engine. Gold isolation is mount +
upload-before-evaluate, not “delete the field in YAML”.

Not a Hub install. `ageval plugin install docker` fail-closes: the id is
reserved.
