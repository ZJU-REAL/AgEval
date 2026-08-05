# Example B: upstream base + install BORA first-party CLI executors.
FROM python:3.12-slim-bookworm
USER root
COPY environment/install-executors.sh /tmp/install-executors.sh
RUN bash /tmp/install-executors.sh && rm -f /tmp/install-executors.sh
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin bora \
    && mkdir -p /attempt/workspace /attempt/package /attempt/artifacts \
    && chown -R bora:bora /attempt
USER bora
WORKDIR /attempt/workspace
ENV PATH="/usr/local/bin:/home/bora/.local/bin:${PATH}"
