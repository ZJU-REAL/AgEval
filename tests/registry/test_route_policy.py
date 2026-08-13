"""Route table requires an access policy; dispatch cannot skip ACL."""

from __future__ import annotations

import pytest
from services.registry.access import AccessPolicy
from services.registry.routes import ROUTES, Route
from services.registry.store import TokenInfo


def test_every_route_declares_access() -> None:
    allowed = {"none", "bearer", "publish", "results_upload", "org_owner", "result_manage"}
    for route in ROUTES:
        assert route.access in allowed, route.name


def test_route_without_access_cannot_be_constructed() -> None:
    with pytest.raises(TypeError):
        Route("GET", "oops", exact="/oops")  # type: ignore[call-arg]


def test_publish_access_requires_scope() -> None:
    policy = AccessPolicy(meta=object())
    denied = policy.enforce_route_access(
        "publish",
        TokenInfo(scopes=frozenset({"read"}), user_id="alice"),
        kwargs={},
    )
    assert denied is not None
    assert denied[0] == 401
    ok = policy.enforce_route_access(
        "publish",
        TokenInfo(scopes=frozenset({"registry:publish"}), user_id="alice"),
        kwargs={},
    )
    assert ok is None
