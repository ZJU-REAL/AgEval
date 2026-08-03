# Authority & conflict resolution

## Chain

```text
docs/design/*  →  ARCHITECTURE.md  →  specs/ROADMAP.md  →  Active Spec  →  code/tests/examples
```

Optional: `specs/constitution/*` only for user-fixed implementation decisions; never replaces design.

## Conflict handling

1. Stop the conflicting implementation.
2. Classify: design change | structure change | version scope | implementation drift.
3. Edit the **highest** authority first.
4. Sync README / AGENTS / Specs / tests in the same change when claims change.

## What skills are not

- Not a second design doc.
- Not a license to claim unfinished Roadmap surfaces as available.
- Not allowed to invent `bora` subcommands not present in `src/bora/cli/main.py`.
