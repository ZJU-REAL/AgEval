# README hero source

`../hero.png` and `../hero.zh-CN.png` are composed by `render_hero.py` (Pillow, 1680×600, bake at 2× then LANCZOS).

This folder is the editable source: copy, type size, and owl position live in the script. Lockup is `owl-black.png` / `owl-black.svg`; pixel wash is `owl-wash.png` (also generated in-script).

## Export on this Mac

Needs Pillow and `rsvg-convert` (`brew install librsvg`). Homebrew Python has no Pillow, so use the local venv:

```bash
cd docs/assets/hero-source
python3 -m venv .venv          # once
.venv/bin/pip install pillow   # once
.venv/bin/python render_hero.py
```

`rsvg-convert` is resolved from PATH, then `/opt/homebrew/bin`. Outputs:

- `docs/assets/hero.png`
- `docs/assets/hero.zh-CN.png`
- `hero-en@2x.png` / `hero-zh@2x.png` and 900-wide previews stay in this folder (gitignored)

`.venv/` is gitignored. Do not commit unless asked.
