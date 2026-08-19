# Authority & conflict resolution

## Chain

```text
docs/design/*  →  ARCHITECTURE.md  →  GitHub Issues  →  code/tests/examples
```

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
