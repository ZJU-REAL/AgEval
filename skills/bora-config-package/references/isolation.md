# Isolation notes for package authors

## Gold / evaluation material

- Put hidden labels under `evaluation/` (or package paths never mounted to Agent).
- On Docker L1, package view filters evaluation material from harness/agent.
- Evaluator receives allowlisted staged inputs only after writer barrier.

## Provider

- `provider.kind: local` — L0 path; assurance claims stay l0 unless package is L1.
- `provider.kind: docker` — L1 orchestration. **Package must ship `environment/Dockerfile`**
  (or `provider.dockerfile` relative path). Default official base:
  `FROM bora-attempt:l1` (preinstalls codex / pi / opencode / claude-code).
  Upstream base: `FROM <image>` then install required CLIs in that Dockerfile.
  Secrets never baked into image layers.

## Do not

- Rely on “delete field from yaml” as isolation.
- Mount gold into harness “for convenience”.
- Put credentials in package tree.
