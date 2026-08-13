"""Device / web session auth (GitHub OAuth lives in oauth_github)."""

from __future__ import annotations

from typing import Any

from services.registry.store import TokenInfo


class AuthService:
    def __init__(self, tokens: Any) -> None:
        self.tokens = tokens

    def auth_for(self, raw_token: str | None) -> TokenInfo:
        return self.tokens.auth_for(raw_token)
