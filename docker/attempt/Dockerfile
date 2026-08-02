# BORA L1 Attempt runtime image — non-privileged, no Docker socket.
# Platform fixed at build time (linux/arm64 for this repository's primary path).
FROM python:3.12-slim-bookworm

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin bora \
    && mkdir -p /attempt/workspace /attempt/package /attempt/artifacts \
    && chown -R bora:bora /attempt

USER bora
WORKDIR /attempt/workspace
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/bora/.local/bin:${PATH}"

# Minimal tools for probes (no docker client)
RUN python -c "import sys; print(sys.version)"

CMD ["python", "-c", "print('bora-attempt-ready')"]
