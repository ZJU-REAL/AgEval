#!/usr/bin/env bash
# Install BORA first-party CLI executors into a Debian/Ubuntu image layer.
# Used by the official base image and by upstream-FROM example Dockerfiles.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y --no-install-recommends nodejs
npm install -g \
  "@openai/codex@0.146.0" \
  "@earendil-works/pi-coding-agent@0.83.0" \
  "opencode-ai@1.18.2" \
  "@anthropic-ai/claude-code@2.1.221"
npm cache clean --force
rm -rf /var/lib/apt/lists/* /tmp/*
command -v codex
command -v pi
command -v opencode
command -v claude || command -v claude-code
