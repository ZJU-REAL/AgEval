# BORA L1 Attempt base image — non-privileged, no Docker socket.
# Preinstalls coding-agent engines + ACP entries (Spec 19 BOM, five entries).
# Build once (docker/attempt/build.py); packages FROM bora-attempt:l1 or extend upstream.
# Python ACP SDK stays on the parent host — never installed here.

FROM python:3.12-slim-bookworm

USER root
COPY install-executors.sh /tmp/install-executors.sh
COPY acp-entries.lock.json /etc/bora/acp-entries.lock.json
RUN bash /tmp/install-executors.sh \
    && rm -f /tmp/install-executors.sh \
    && test -f /etc/bora/acp-entries.lock.json

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin bora \
    && mkdir -p /attempt/workspace /attempt/package /attempt/artifacts \
    && chown -R bora:bora /attempt

# Post-user PATH verify as actor UID 10001 (numeric non-root).
RUN set -e; \
    export PATH="/usr/local/bin:/usr/bin:/bin"; \
    su -s /bin/bash bora -c '\
      command -v codex && command -v codex-acp && \
      command -v pi && command -v pi-acp && \
      command -v opencode && \
      (command -v claude || command -v claude-code) && command -v claude-agent-acp && \
      command -v grok \
    '

USER bora
WORKDIR /attempt/workspace
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:/home/bora/.local/bin:${PATH}"

CMD ["python", "-c", "print('bora-attempt-ready')"]
