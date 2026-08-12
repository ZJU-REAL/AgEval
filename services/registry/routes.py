"""Declarative Registry HTTP route table.

Handlers remain methods on the BaseHTTPRequestHandler subclass; this module
owns *which* path matches *which* handler so ACL call sites stay discoverable
next to the route name rather than buried in do_GET/do_POST chains.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Route:
    method: str
    name: str
    exact: str | None = None
    pattern: str | None = None
    groups: tuple[str, ...] = ()
    # Extra kwargs merged into the handler call (e.g. result_kind).
    fixed: Mapping[str, Any] | None = None
    # Optional path filter after a regex match (package id vs versions subpaths).
    predicate: Callable[[str], bool] | None = None
    # When True, skip bearer resolution (only /health today).
    skip_auth: bool = False
    # Pass query-string dict as ``qs=``.
    pass_qs: bool = False


def _package_id_list_ok(path: str) -> bool:
    rest = path[len("/v1/packages/") :]
    return bool(rest) and "/versions/" not in rest and "/by-digest/" not in rest


ROUTES: tuple[Route, ...] = (
    # GET
    Route("GET", "health", exact="/health", skip_auth=True),
    Route("GET", "list_orgs", exact="/v1/orgs"),
    Route(
        "GET",
        "list_invite_keys",
        pattern=r"/v1/orgs/([^/]+)/invite-keys",
        groups=("org_id",),
    ),
    Route(
        "GET",
        "list_org_members",
        pattern=r"/v1/orgs/([^/]+)/members",
        groups=("org_id",),
    ),
    Route("GET", "get_org", pattern=r"/v1/orgs/([^/]+)", groups=("org_id",)),
    Route("GET", "list_packages", exact="/v1/packages", pass_qs=True),
    Route(
        "GET",
        "list_package_versions",
        pattern=r"/v1/packages/([^/]+(?:/[^/]+)*)",
        groups=("database_id",),
        predicate=_package_id_list_ok,
    ),
    Route(
        "GET",
        "serve_meta",
        pattern=r"/v1/packages/(.+)/versions/([^/]+)",
        groups=("database_id", "version"),
        fixed={"package_digest": None},
    ),
    Route(
        "GET",
        "serve_content",
        pattern=r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})/content",
        groups=("database_id", "package_digest"),
    ),
    Route(
        "GET",
        "serve_package_files_list",
        pattern=r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})/files",
        groups=("database_id", "package_digest"),
    ),
    Route(
        "GET",
        "serve_package_file",
        pattern=r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})/files/(.+)",
        groups=("database_id", "package_digest", "file_path"),
    ),
    Route(
        "GET",
        "serve_package_files_list",
        pattern=r"/v1/packages/(.+)/versions/([^/]+)/files",
        groups=("database_id", "version"),
    ),
    Route(
        "GET",
        "serve_package_file",
        pattern=r"/v1/packages/(.+)/versions/([^/]+)/files/(.+)",
        groups=("database_id", "version", "file_path"),
    ),
    Route(
        "GET",
        "serve_meta",
        pattern=r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})",
        groups=("database_id", "package_digest"),
        fixed={"version": None},
    ),
    Route("GET", "list_attempts", exact="/v1/results/attempts", pass_qs=True),
    Route(
        "GET",
        "serve_attempt_content",
        pattern=r"/v1/results/attempts/([^/]+)/content",
        groups=("run_id",),
    ),
    Route(
        "GET",
        "serve_attempt_file",
        pattern=r"/v1/results/attempts/([^/]+)/files/(.+)",
        groups=("run_id", "file_path"),
    ),
    Route(
        "GET",
        "serve_attempt_files_list",
        pattern=r"/v1/results/attempts/([^/]+)/files",
        groups=("run_id",),
    ),
    Route(
        "GET",
        "list_result_shares",
        pattern=r"/v1/results/attempts/([^/]+)/shares",
        groups=("result_id",),
        fixed={"result_kind": "attempt"},
    ),
    Route(
        "GET",
        "serve_attempt_meta",
        pattern=r"/v1/results/attempts/([^/]+)",
        groups=("run_id",),
    ),
    Route("GET", "list_suites", exact="/v1/results/suites", pass_qs=True),
    Route(
        "GET",
        "serve_suite_content",
        pattern=r"/v1/results/suites/([^/]+)/content",
        groups=("suite_run_id",),
    ),
    Route(
        "GET",
        "list_result_shares",
        pattern=r"/v1/results/suites/([^/]+)/shares",
        groups=("result_id",),
        fixed={"result_kind": "suite"},
    ),
    Route(
        "GET",
        "serve_suite_meta",
        pattern=r"/v1/results/suites/([^/]+)",
        groups=("suite_run_id",),
    ),
    # POST
    Route("POST", "auth_device_code", exact="/v1/auth/github/device/code", skip_auth=True),
    Route("POST", "auth_device_poll", exact="/v1/auth/github/device/poll", skip_auth=True),
    Route("POST", "auth_web_start", exact="/v1/auth/github/web/start", skip_auth=True),
    Route("POST", "auth_web_callback", exact="/v1/auth/github/web/callback", skip_auth=True),
    Route("POST", "create_org", exact="/v1/orgs", skip_auth=True),
    Route("POST", "join_org_with_invite", exact="/v1/orgs/join", skip_auth=True),
    Route(
        "POST",
        "claim_org",
        pattern=r"/v1/orgs/([^/]+)/claim",
        groups=("org_id",),
        skip_auth=True,
    ),
    Route(
        "POST",
        "leave_org",
        pattern=r"/v1/orgs/([^/]+)/leave",
        groups=("org_id",),
        skip_auth=True,
    ),
    Route(
        "POST",
        "create_invite_key",
        pattern=r"/v1/orgs/([^/]+)/invite-keys",
        groups=("org_id",),
        skip_auth=True,
    ),
    Route(
        "POST",
        "add_org_member",
        pattern=r"/v1/orgs/([^/]+)/members",
        groups=("org_id",),
        skip_auth=True,
    ),
    Route("POST", "publish_package", exact="/v1/packages", skip_auth=True),
    Route("POST", "upload_attempt", exact="/v1/results/attempts", skip_auth=True),
    Route("POST", "upload_suite", exact="/v1/results/suites", skip_auth=True),
    Route(
        "POST",
        "add_result_share",
        pattern=r"/v1/results/attempts/([^/]+)/shares",
        groups=("result_id",),
        fixed={"result_kind": "attempt"},
        skip_auth=True,
    ),
    Route(
        "POST",
        "add_result_share",
        pattern=r"/v1/results/suites/([^/]+)/shares",
        groups=("result_id",),
        fixed={"result_kind": "suite"},
        skip_auth=True,
    ),
    # DELETE
    Route(
        "DELETE",
        "revoke_invite_key",
        pattern=r"/v1/orgs/([^/]+)/invite-keys/([^/]+)",
        groups=("org_id", "key_id"),
        skip_auth=True,
    ),
    Route(
        "DELETE",
        "remove_org_member",
        pattern=r"/v1/orgs/([^/]+)/members/([^/]+)",
        groups=("org_id", "user_id"),
        skip_auth=True,
    ),
    Route(
        "DELETE",
        "delete_org",
        pattern=r"/v1/orgs/([^/]+)",
        groups=("org_id",),
        skip_auth=True,
    ),
    Route(
        "DELETE",
        "remove_result_share",
        pattern=r"/v1/results/attempts/([^/]+)/shares",
        groups=("result_id",),
        fixed={"result_kind": "attempt"},
        skip_auth=True,
    ),
    Route(
        "DELETE",
        "remove_result_share",
        pattern=r"/v1/results/suites/([^/]+)/shares",
        groups=("result_id",),
        fixed={"result_kind": "suite"},
        skip_auth=True,
    ),
    Route(
        "DELETE",
        "delete_attempt",
        pattern=r"/v1/results/attempts/([^/]+)",
        groups=("run_id",),
        skip_auth=True,
    ),
    Route(
        "DELETE",
        "delete_suite",
        pattern=r"/v1/results/suites/([^/]+)",
        groups=("suite_run_id",),
        skip_auth=True,
        pass_qs=True,
    ),
    Route(
        "DELETE",
        "delete_package_release",
        pattern=r"/v1/packages/(.+)/versions/([^/]+)",
        groups=("database_id", "version"),
        skip_auth=True,
    ),
    # PATCH
    Route(
        "PATCH",
        "patch_attempt",
        pattern=r"/v1/results/attempts/([^/]+)",
        groups=("run_id",),
        skip_auth=True,
    ),
    Route(
        "PATCH",
        "patch_suite",
        pattern=r"/v1/results/suites/([^/]+)",
        groups=("suite_run_id",),
        skip_auth=True,
    ),
    Route(
        "PATCH",
        "patch_package_release",
        pattern=r"/v1/packages/(.+)/versions/([^/]+)",
        groups=("database_id", "version"),
        skip_auth=True,
    ),
)


def match_route(method: str, path: str) -> tuple[Route, dict[str, Any]] | None:
    """Return the first matching route and captured kwargs (excluding auth/qs)."""
    for route in ROUTES:
        if route.method != method:
            continue
        if route.exact is not None:
            if path == route.exact:
                kwargs = dict(route.fixed or {})
                return route, kwargs
            continue
        if route.pattern is None:
            continue
        m = re.fullmatch(route.pattern, path)
        if not m:
            continue
        if route.predicate is not None and not route.predicate(path):
            continue
        kwargs = dict(route.fixed or {})
        for i, name in enumerate(route.groups):
            kwargs[name] = m.group(i + 1)
        return route, kwargs
    return None
