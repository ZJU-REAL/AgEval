#!/usr/bin/env python3
"""Machine-check web UI tokens against docs/design/13-web-ui-tokens.md.

Checks:
  1. Doc table and the CANONICAL dict in this script agree (both directions).
  2. Mapped CSS variables in the three apps only ever hold canonical values.
  3. No raw hex outside the token/theme files and owl brand assets.

Run: python3 scripts/check_design_tokens.py  (exit 1 on any failure)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs/design/13-web-ui-tokens.md"

# token -> (light, dark)
CANONICAL: dict[str, tuple[str, str]] = {
    "canvas": ("#F4F5F8", "#11141C"),
    "canvas-soft": ("#E8EAF1", "#1A1E2A"),
    "canvas-soft-2": ("#E4E7F0", "#222738"),
    "hairline": ("#D5D8E2", "#2A2F3E"),
    "ink": ("#14161F", "#EEF0F6"),
    "body": ("#4A4E5C", "#9AA0B4"),
    "mute": ("#7A7F90", "#6E7488"),
    "link": ("#1B54E8", "#5B7BFF"),
    "link-deep": ("#001F73", "#8AA0FF"),
    "error": ("#EE0000", "#FF5C5C"),
    "warning": ("#F5A623", "#F5A623"),
    "code-bg": ("#F4F5F8", "#0C0E14"),
    "accent": ("#5B7BFF", "#002FA7"),
}

# (file, css var, canonical token, required)
VAR_MAP: list[tuple[str, str, str, bool]] = [
    # hub / viewer (identical --viewer-* vocabulary, values checked per file)
    *(
        (f"apps/{app}/src/index.css", f"--viewer-{var}", token, True)
        for app in ("hub", "viewer")
        for var, token in [
            ("canvas", "canvas"),
            ("canvas-soft", "canvas-soft"),
            ("canvas-soft-2", "canvas-soft-2"),
            ("hairline", "hairline"),
            ("ink", "ink"),
            ("body", "body"),
            ("mute", "mute"),
            ("link", "link"),
            ("link-deep", "link-deep"),
            ("error", "error"),
            ("warning", "warning"),
            ("code-bg", "code-bg"),
            ("row-hover", "canvas-soft"),
        ]
    ),
    # docs (fumadocs vars + prose link vars)
    ("website/src/app/global.css", "--color-fd-background", "canvas", True),
    ("website/src/app/global.css", "--color-fd-foreground", "ink", True),
    ("website/src/app/global.css", "--color-fd-muted", "canvas-soft", True),
    ("website/src/app/global.css", "--color-fd-muted-foreground", "body", True),
    ("website/src/app/global.css", "--color-fd-secondary", "canvas-soft-2", True),
    ("website/src/app/global.css", "--color-fd-primary", "link", True),
    ("website/src/app/global.css", "--color-fd-ring", "link", True),
    ("website/src/app/global.css", "--color-fd-border", "hairline", True),
    ("website/src/app/global.css", "--ageval-link", "link", True),
    ("website/src/app/global.css", "--ageval-link-deep", "link-deep", True),
    # landing accents
    ("website/src/components/landing/landing.css", "--accent", "accent", True),
    ("website/src/components/landing/landing.css", "--accent-deep", "accent", True),
]

# Hex literals are allowed only in these files (token definitions + owl assets).
HEX_ALLOWLIST = {
    "website/src/app/global.css",
    "website/src/components/landing/landing.css",
    "apps/hub/src/index.css",
    "apps/viewer/src/index.css",
    "website/src/components/owl-flat.tsx",
    "apps/hub/src/components/owl-icon.tsx",
    "apps/viewer/src/components/owl-icon.tsx",
}

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
ASSIGN_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def norm(hexes: list[str]) -> set[str]:
    return {h.lower() for h in hexes}


def check_doc(errors: list[str]) -> None:
    text = DOC.read_text(encoding="utf-8")
    section = re.search(r"## 色彩令牌\n(.*?)\n## ", text, re.S)
    if not section:
        errors.append("doc: '## 色彩令牌' section not found")
        return
    doc_tokens: dict[str, set[str]] = {}
    for line in section.group(1).splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("令牌", "---", ":---") or set(cells[0]) <= {"-", ":"}:
            continue
        name = re.sub(r"（.*?）|\(.*?\)", "", cells[0]).replace("`", "").strip()
        doc_tokens[name] = norm(HEX_RE.findall(line))
    missing = set(CANONICAL) - set(doc_tokens)
    extra = set(doc_tokens) - set(CANONICAL)
    if missing:
        errors.append(f"doc: tokens missing from table: {sorted(missing)}")
    if extra:
        errors.append(f"doc: unknown tokens in table: {sorted(extra)}")
    for name, hexes in doc_tokens.items():
        want = norm(list(CANONICAL.get(name, ())))
        absent = want - hexes
        if absent:
            errors.append(f"doc: row '{name}' lacks canonical value(s) {sorted(absent)}")


def check_vars(errors: list[str]) -> None:
    by_file: dict[str, dict[str, set[str]]] = {}
    for rel, var, _token, _req in VAR_MAP:
        if rel not in by_file:
            assigns: dict[str, set[str]] = {}
            for m in ASSIGN_RE.finditer((REPO / rel).read_text(encoding="utf-8")):
                assigns.setdefault(m.group(1), set()).update(norm(HEX_RE.findall(m.group(2))))
            by_file[rel] = assigns
        values = by_file[rel].get(var)
        if values is None:
            errors.append(f"{rel}: variable {var} not defined")
            continue
        token = next(t for f, v, t, _ in VAR_MAP if f == rel and v == var)
        allowed = norm(list(CANONICAL[token]))
        bad = values - allowed
        if bad:
            errors.append(f"{rel}: {var} holds non-canonical {sorted(bad)} (token '{token}' allows {sorted(allowed)})")


def check_raw_hex(errors: list[str]) -> None:
    for root in ("website/src", "apps/hub/src", "apps/viewer/src"):
        for path in (REPO / root).rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".css"} or not path.is_file():
                continue
            rel = path.relative_to(REPO).as_posix()
            if rel in HEX_ALLOWLIST:
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if HEX_RE.search(line):
                    errors.append(f"{rel}:{i}: raw hex outside token files: {HEX_RE.search(line).group(0)}")


def main() -> int:
    errors: list[str] = []
    check_doc(errors)
    check_vars(errors)
    check_raw_hex(errors)
    if errors:
        print("design-token check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("design-token check OK (doc + hub/viewer + website in sync)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
