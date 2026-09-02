# Authority & conflict resolution

## Chain

```text
docs/design/*  →  ARCHITECTURE.md  →  GitHub Issues  →  code/tests/examples
```

`docs/` is self-contained. Do not read an external BRIEF / vault as design truth.

`ARCHITECTURE.md` 拥有 Current 源码树、依赖图、五个阶段状态机、emit 图、数据流表、失败归属。施工红线与 CI 命令在根 `AGENTS.md`。不要在 skill 里复制那两份图。

`website/` is reader-facing product documentation only — never design truth.  
`apps/*` and `services/*` READMEs own SPA/service **dev** detail, not product tutorials.

## Conflict handling

1. Stop the conflicting implementation.
2. Classify: design change | structure change | delivery scope | implementation drift.
3. Edit the **highest** authority first.
4. Sync README / AGENTS / website / tests in the same change when claims change.

## What skills are not

- Not a second design doc.
- Not a license to claim unfinished surfaces as available.
- Not allowed to invent `ageval` subcommands not present in `src/ageval/cli/main.py`.
