#!/usr/bin/env bash
# Run at end of env prepare (plugin multi handler). Observable readiness marker.
set -euo pipefail
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
echo "slot-probe ok ${ts}" > post_setup.ok
echo "slot-probe post_setup wrote $(pwd)/post_setup.ok"
