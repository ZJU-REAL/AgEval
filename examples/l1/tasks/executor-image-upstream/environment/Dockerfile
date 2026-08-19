# Example B: upstream base + install ageval first-party CLI executors.
FROM python:3.12-slim-bookworm
USER root
COPY environment/install-executors.sh /tmp/install-executors.sh
RUN bash /tmp/install-executors.sh && rm -f /tmp/install-executors.sh
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin ageval \
    && mkdir -p /attempt/workspace /attempt/package /attempt/artifacts \
    && chown -R ageval:ageval /attempt
USER ageval
WORKDIR /attempt/workspace
ENV PATH="/usr/local/bin:/home/ageval/.local/bin:${PATH}"
