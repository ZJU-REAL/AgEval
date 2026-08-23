# docker environment

First-party exclusive-slot winner for `environment: docker`.

The Attempt runs in a container built from the task's own recipe (plus
plugin `image_layers` when declared). The official Attempt image bakes
coding-agent ACP entries at **build** time; invoke does not `npm i`.
Container id, `docker exec -u/-w`, and UID/GID stay in this package.
ACP / `run.py` / Core never see `container_id`.

## Bind

```yaml
environment: docker
```

The host needs a working Docker engine. Gold isolation is mount +
upload-before-evaluate, not “delete the field in YAML”.

Not a Hub install. `ageval plugin install docker` fail-closes: the id is
reserved.
