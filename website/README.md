# ageval documentation website

Bilingual Fumadocs site for **ageval**.

This directory is a **reader-facing product projection**. It does **not**:

- own design or delivery truth
- import production `src/ageval` runtime packages
- replace `apps/viewer` (local suite UI) or `apps/hub` (Registry SPA)

## Authority boundary

| Surface                        | Role                                                               |
| ------------------------------ | ------------------------------------------------------------------ |
| `docs/design/` + `docs/PRD.md` | Mechanism / product design authority                               |
| `ARCHITECTURE.md`              | Module structure authority                                         |
| GitHub Issues                  | Delivery tracking                                                  |
| **`website/` (this tree)**     | How-to and product navigation (rewritten; not a mirror of `docs/`) |
| `apps/*` / `services/*` README | SPA / service **dev** detail                                       |

Conflict → fix `docs/` (or Architecture / Issues) first, then sync this site.

## References (scaffold & IA)

| Purpose                        | Remote                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Framework, visual system, i18n | [`ZJU-REAL/BORA-v1`](https://github.com/ZJU-REAL/BORA-v1) → `website/`                                       |
| Content module grouping (IA)   | Historical v0 site sections: `index` / `get-started` / `concepts` / `protocols` / `operations` / `developer` |

## Local development

From the monorepo root:

```sh
pnpm --dir website install
pnpm --dir website dev
```

Open `http://localhost:3000`. Default locale is Simplified Chinese at `/zh-CN`; English at `/en`.

| Env | Meaning |
| --- | --- |
| `NEXT_PUBLIC_HUB_URL` | Homepage CTA and docs sidebar link to the Hub SPA. Unset = `http://127.0.0.1:5174`. Empty = hide. |

## Content layout

- `content/docs/*.mdx` — Simplified Chinese (default locale)
- `content/docs/*.en.mdx` — English, same slug
- `content/docs/**/meta.json` — Chinese navigation
- `content/docs/**/meta.en.json` — English navigation

### Information architecture (job-oriented)

```text
index
getting-started/   # 入门：install, first-run
run/               # 运行：single-task, suite, switch-agent, campaign, viewer, export
author/            # 编写 Dataset：tutorial, layout, harness, evaluator, docker, provenance
agents/            # Agent 接入：acp-profiles, multi-agent, l1-docker
share/             # 结果共享：registry, hub
reference/         # 参考：cli, config-fields, results, examples
contribute/        # 贡献：architecture, contributing
```

Writing rules: usage-path IA with professional product tone; bilingual zh-CN / en; no whole-page mirror of `docs/design`.

## Design system

[DESIGN.md](DESIGN.md) defines one chrome: Klein Blue + cool ink, shared by landing and docs (Anton wordmark on landing; Geist / Noto Sans SC everywhere else).

## Checks

```sh
pnpm --dir website lint
pnpm --dir website typecheck
pnpm --dir website build
```

## Self-host (Docker)

The site runs as a **Next.js standalone server** — the search API (`/api/search`, Mandarin tokenizer) and the i18n middleware need a Node runtime; TLS stays on the operator's Caddy/nginx in front.

From the repo root:

```sh
# build locally
docker compose -f website/docker-compose.yml up -d --build

# or pull a released image
export AGEVAL_IMAGE_TAG=<tag>
docker compose -f website/docker-compose.yml pull && docker compose -f website/docker-compose.yml up -d
```

Serves on port `3000`. `NEXT_PUBLIC_HUB_URL` (Hub SPA link on homepage/docs sidebar) is **build-time**; pass it as an env when building:

```sh
NEXT_PUBLIC_HUB_URL=https://hub.example.com docker compose -f website/docker-compose.yml build
```

## Not in scope here

- Hub / Viewer feature work (those live under `apps/`)
