# BORA L1 Attempt base image — non-privileged, no Docker socket.
# Preinstalls first-party CLI executors: codex, pi, opencode, claude-code.
# Build once (docker/attempt/build.py); packages FROM bora-attempt:l1 or extend upstream.

FROM python:3.12-slim-bookworm

USER root
COPY install-executors.sh /tmp/install-executors.sh
RUN bash /tmp/install-executors.sh && rm -f /tmp/install-executors.sh

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin bora \
    && mkdir -p /attempt/workspace /attempt/package /attempt/artifacts \
    && chown -R bora:bora /attempt

USER bora
WORKDIR /attempt/workspace
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:/home/bora/.local/bin:${PATH}"

CMD ["python", "-c", "print('bora-attempt-ready')"]
