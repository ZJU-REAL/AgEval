# ssh environment

First-party exclusive-slot winner for `environment: ssh`. Implementation:
`src/ageval/plugins/contrib/ssh/host.py`. Protocol verbs only; no vendor
handle leaks into ACP / `run.py`.

## A vs B

`environment_options.image` empty → **A**: the remote machine is the box.
`attach_stdio` is `ssh -T -- argv`.

A non-empty **existing** image tag → **B**: `start()` does remote `docker run`
of that tag; `attach_stdio` is `ssh -- docker exec -i`. The image must already
exist on the host. Nothing is baked at invoke.

Locators (`host` / `user` / `port` / `key_env`) are resolved at preflight.
Keys never enter the lock.

## ACP over ssh A is a known gap

Product ACP is a **parent-only** JSON-RPC client over `attach_stdio` (stdio).
Official ACP **stdio** is a local subprocess pipe:

- [Transports (v1)](https://agentclientprotocol.com/protocol/v1/transports)

Official **remote** transport is still an RFD (Streamable HTTP + WebSocket), not
stdio tunneled over SSH:

- [Streamable HTTP & WebSocket Transport](https://agentclientprotocol.com/rfds/streamable-http-websocket-transport)
- [Introduction](https://agentclientprotocol.com/get-started/introduction)

On ssh A, `initialize` can complete and `session/new` on the same SSH pipe can
fail (`-32603`, stream destroyed) with pi-acp. That is a **transport** gap, not
a missing entry or missing key.

Until the official remote transport is consumable from the parent client:

- Do **not** claim ssh A × live ACP stdio as a supported path.
- Prefer exec-style executors (`dsh` / `nooa`) on ssh A.
- Do **not** invent a private HTTP/WS stack, a file-dump “ACP session”, or a
  second vendor stdout scrape.
- ssh B (`docker exec -i` over SSH) is a different privilege/image problem; do
  not treat a stdio-over-SSH failure as “B is broken” or the reverse.

## Other verbs

`exec` / `upload` / `download` are the Protocol surface for in-box workers.
Directory `upload` / `download` copy **contents** (not a nested `dest/src`).
Agent Service does not harvest the box workspace after every invoke. After
writers stop, the run phase downloads **missing** publishable files from
`/attempt/workspace` onto parent `task-artifacts`.
