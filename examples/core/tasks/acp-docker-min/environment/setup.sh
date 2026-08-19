#!/bin/sh
# Last slot of the environment phase: this task's own preparation, never the
# Agent runtime. Also the honest place to check that gold has not arrived: the
# Agent is about to run, and it must not be able to read the answer.
set -eu
test -f /etc/ageval-box-marker
if [ -d "$AGEVAL_EVALUATION" ]; then
  echo "gold is visible before the Agent ran: $AGEVAL_EVALUATION" >&2
  exit 1
fi
echo "setup ok" > "$AGEVAL_WORKSPACE/.setup-ran"
