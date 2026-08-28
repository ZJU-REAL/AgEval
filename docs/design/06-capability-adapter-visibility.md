# 06 — 能力与可见性

环境报 `capabilities`。task `requires.environment` 非空则必须是子集，否则 lock 失败。Result 记 `kind` + `capabilities_used`。

常见 cap：`exec`、`upload`、`download`、`attach_stdio`、`uid_gid`、`path_views`、`compose`。四 kind 矩阵见 [05-runtime/environment.md](05-runtime/environment.md)。e2b/ssh 不报 compose / uid_gid。契约：`src/ageval/environments/protocol.py`。不能兑现的 cap 不许报 yes。

## gold

默认隔离是时间切：environment / run 不 upload `evaluation/`。evaluate 开头再 upload，然后环境内 exec evaluator。不要只靠 YAML 删字段。

```text
environment/run     /attempt/evaluation  不存在
evaluate 开头       host.upload(evaluation_src, /attempt/evaluation)
                    然后 exec evaluator.py
```

`path_views` 是额外能力，只有 docker 这类能兑现的 kind 才报 yes。UID/GID 同理。

凭证：locator only；投影最小集进获准进程。不进 lock / evidence。见 ARCHITECTURE § Failure and Privacy Boundary。
