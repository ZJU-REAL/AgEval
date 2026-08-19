#!/bin/sh
# Environment's last slot: prove the sidecar is reachable from inside the box
# and leave the finding where the evaluator can read it.
set -eu
python3 "$(dirname "$0")/probe_db.py"
