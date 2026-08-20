## Summary

<!-- What changed and why. Mechanism / product-semantics changes must update docs/design first (or say it already did). -->

## Related

- Issue:
- Evidence grade (if claimed):

## Verification

```bash
# Commands actually run (pytest / ageval lock|run / validate…)
```

## Checklist

- [ ] No credentials / tokens in yaml, lock, evidence, or examples
- [ ] Trajectory / `HarnessTerminal.completed` is not treated as PASS
- [ ] Product / mechanism changes updated the highest authority (design → Architecture / Issues as needed)
- [ ] Regression or public smoke exists; a fixture alone is not `runnable-mvp`
