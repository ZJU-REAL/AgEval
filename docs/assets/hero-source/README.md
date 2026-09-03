# README hero source

`render_hero.py` bakes the README posters (Pillow, 1680×600, compose at 2× then LANCZOS) and overwrites:

- `docs/assets/hero.png`
- `docs/assets/hero.zh-CN.png`

This folder is the editable source: copy, type size, and owl position live in the script. Lockup is `owl-black.png` / `owl-black.svg`; pixel wash is `owl-wash.png` (also generated in-script).

## Export

Needs Pillow and `rsvg-convert` (`brew install librsvg`). Homebrew Python has no Pillow, so use the local venv:

```bash
cd docs/assets/hero-source
python3 -m venv .venv          # once
.venv/bin/pip install pillow   # once
.venv/bin/python render_hero.py
```

Output names match the README embeds. `rsvg-convert` is resolved from PATH, then Homebrew. `.venv/` is gitignored.
