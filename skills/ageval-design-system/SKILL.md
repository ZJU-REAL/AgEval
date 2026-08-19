---
name: ageval-design-system
description: >
  ageval web UI style rules for coding agents editing website (landing + docs),
  apps/hub, or apps/viewer: canonical color tokens (cool paper/ink + IKB
  #1B54E8/#5B7BFF), font stacks (Geist/Anton wordmark-only), chamfer/radius,
  focus and selection language, the ten invariants, and the machine check
  scripts/check_design_tokens.py. Use when adding or restyling UI in any of the
  three web surfaces, picking colors or fonts, adding icons, or when a change
  touches raw hex, focus rings, buttons, or the owl brand assets. Authority is
  docs/design/13-web-ui-tokens.md; this skill only routes and summarizes.
---

# ageval web UI design system

Three surfaces, one language: website landing, website docs (fumadocs),
hub SPA, viewer SPA. Authority: `docs/design/13-web-ui-tokens.md`.

## Where tokens live

| Surface      | Token file                                                              |
| ------------ | ----------------------------------------------------------------------- |
| hub / viewer | `apps/{hub,viewer}/src/index.css` (`--viewer-*` + `@theme`)             |
| docs         | `website/src/app/global.css` (`--color-fd-*`, `--ageval-link*`)           |
| landing      | Token block at the top of `website/src/components/landing/landing.css`  |

Change order: edit the table in `docs/design/13` first → sync script `CANONICAL` →
sync the surface files → run the machine check. If the three surfaces disagree,
fix the surfaces to match docs/13 + the script.

## Quick rules (full list in docs/design/13)

- Hex values live only in token files and owl brand assets. App code uses semantic
  names (`text-ink`, `border-hairline`, …).
- IKB (`link` / `primary`) is for links, focus, primary CTAs, and brand slots.
  Do not use it as a large fill.
- `mute` is never body text. `canvas*` is surface, `hairline` is line,
  `ink` / `body` / `mute` are type.
- Anton is wordmark-only. Body is Geist (+ CJK fallback). Mono is Geist Mono.
- Radii are 6 / 8 / 12px only. Primary CTA (SPA Button `default`) is IKB fill +
  `chamfer chamfer-focus` + mono 13px. Chamfered controls use `chamfer-focus`
  (drop-shadow stroke; ink stroke on IKB fill).
- Underline tabs are `font-mono text-xs uppercase tracking-wide` with an IKB
  active underline. Page heads use `PageHead` (h1 + optional sub + hairline;
  no numbered kicker).
- Focus: buttons `ring-2 ring-link/70`; fields `border-link` 1px, no extra ring;
  landing 3px outline.
- Popover shadow is `--viewer-shadow-pop` only. Phase charts use
  `--viewer-phase-1..6` only.
- Icons: brand uses owl (`website/src/components/owl-flat.tsx`, each SPA
  `OwlIcon`); function icons use lucide. Do not add a third set.

## Machine check

```bash
python3 scripts/check_design_tokens.py
```

Checks: docs/13 table ↔ script `CANONICAL` both ways; mapped variables stay
inside the canonical set; no raw hex in app code (outside the allowlist).
CI job `design-tokens` runs the same command. Run it locally after token or
style edits.
