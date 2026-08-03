# Harness antipatterns

| Antipattern | Do instead |
| --- | --- |
| Treat `completed` as PASS | Independent evaluator only |
| `if executor == "codex":` in harness for Core policy | Switch `agent_profiles` / `active_profile` |
| Read `~/.codex/auth.json` or print secrets | Rely on Runtime projection |
| Write training JSON by hand under package | Use Agent Service trajectory under Result.logs |
| Soft CallLimit as the only hard ceiling | `limits.agent_invocations` in yaml (Runtime) |
| Import evaluation gold into harness | Keep gold unmounted; materialize post-barrier |
| Branch on task_id / benchmark name in Core path | Mechanism-only adapters |
