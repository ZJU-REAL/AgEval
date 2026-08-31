#!/bin/sh
# Start the in-box PostgreSQL, load the seed, and publish the env handoff meta.
# Runs as the box user (non-root) via the default environment_setup chain;
# postgres refuses only root, so the current user is a valid server owner.
set -eu

PGBIN=$(ls -d /usr/lib/postgresql/*/bin | head -n 1)
PGDATA=/tmp/pgdata
export PGDATA
export PATH="$PGBIN:$PATH"

mkdir -p "$PGDATA"
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  initdb -D "$PGDATA" -A trust -U ageval > /tmp/pg-init.log 2>&1
fi
# The apt socket dir /var/run/postgresql is postgres-owned; the box user
# cannot write it, so keep both TCP and the unix socket under our control.
pg_ctl -D "$PGDATA" -l /tmp/pg.log \
  -o "-c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp" -w start

createdb -h 127.0.0.1 ageval 2>/dev/null || true
psql -h 127.0.0.1 -d ageval -v ON_ERROR_STOP=1 -q -f "$PWD/seed.sql"

# Env handoff meta: the harness reads this to reach the seeded database.
# container = box hostname (parent-side `docker exec` accepts it).
cat > /attempt/workspace/.ageval_env_result.json <<EOF
{"ok": true, "container": "$(hostname)", "host": "127.0.0.1", "user": "ageval", "database": "ageval", "password": "ageval-attempt"}
EOF
