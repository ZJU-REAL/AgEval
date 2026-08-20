---
name: ageval-plugin
description: >
  Author ageval.plugin/1: exclusive and chain slots, registry resolve, environment
  or executor winners, image_layers bake. Use for plugin.yaml, attach_stdio hosts,
  trajectory_collect. Not an app store. Never invent slots.
---

# ageval plugins

Host declares slots in `src/ageval/plugins/slots.py`. Plugins fill them.

| Kind | Meaning | Examples |
| --- | --- | --- |
| exclusive | One winner = same-name service | `environment`, `executor` |
| chain | `(ctx, value, nxt)` | `after_environment_ready`, `environment_setup`, `trajectory_collect` |

`ageval plugin install` writes `~/.ageval/plugins` only. Never rewrites profiles.

inject: `service: environment`. ACP needs `attach_stdio`. In-box workers
(dsh / nooa) need `exec` and `upload`. Do not pin `plugin_id: e2b`.

Name by mechanism (`acp`, `e2b`, `ssh`, `nooa`). First-party lives in `src/ageval/plugins/contrib/`. External packages under `plugins/`.

Recognition ≠ this host can run ≠ image baked. Missing extra / key → skip, do not fake green.

Authoring: [references/authoring.md](references/authoring.md). Mechanism: [references/mechanism.md](references/mechanism.md). Design: `docs/design/11-extension-plugins.md`.
