"""Registry package / result media types (client + server shared)."""

from __future__ import annotations

DATABASE_MEDIA_TYPE = "application/vnd.bora.database.v1.tar+gzip"
PLUGIN_MEDIA_TYPE = "application/vnd.bora.plugin.v1.tar+gzip"
AGENT_MEDIA_TYPE = "application/vnd.bora.agent.v1.tar+gzip"
ATTEMPT_RESULT_MEDIA_TYPE = "application/vnd.bora.attempt-result.v1.tar+gzip"
SUITE_RESULT_MEDIA_TYPE = "application/vnd.bora.suite-result.v1.tar+gzip"
