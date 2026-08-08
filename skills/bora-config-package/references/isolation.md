# Isolation notes for package authors

## Gold / evaluation material

- Put hidden labels under `evaluation/` (or package paths never mounted to Agent).
- On Docker L1, package view filters evaluation material from harness/agent.
- Evaluator receives allowlisted staged inputs only after writer barrier.

## Provider

- `provider.kind: local` — L0 path; assurance claims stay l0 unless package is L1.
- `provider.kind: docker` — L1 orchestration. **Package must ship `environment/Dockerfile`**
  (or `provider.dockerfile` relative path). Default official base:
  `FROM bora-attempt:l1` — build-time bake-in of minimum ACP **entries** (engine + ACP
  inlet for Mode 1): codex / claude-code / pi / opencode / grok-build
  (see docs/design/05-runtime/provider-l1.md).
  Upstream base: `FROM <image>` then install required ACP entries in that Dockerfile.
  Secrets never baked into image layers.
- Coding agents on L1: `executor: acp` + `options.entry`; parent ACP client +
  `docker exec` placement — no private CLI scrape.

## Do not

- Rely on “delete field from yaml” as isolation.
- Mount gold into harness “for convenience”.
- Put credentials in package tree.
