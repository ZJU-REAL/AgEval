"""L0 vs L1 probe: declared imports, bake-declared, no lock digest mutation."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.application.composition import build_lock_command, build_probe_command
from bora.plugins.store import install_from_path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "tests/fixtures/plugins/host-probe"
DB = ROOT / "tests/fixtures/databases/probe-min"
SECRET = "sk-probe-must-never-appear"


@pytest.fixture()
def bora_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "bora-home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins import bootstrap as boot
    from bora.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    install_from_path(PLUGIN)
    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    return home


def _vendor_sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "host_probe_vendor_sdk.py").write_text("present = True\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib

    importlib.invalidate_caches()


def test_l0_missing_import_fails_probe(bora_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del bora_home
    monkeypatch.delenv("PROBE_API_KEY", raising=False)
    payload, ready = build_probe_command().run(
        database_root=DB,
        task_id="l0-task",
        environ={},
    )
    assert ready is False
    assert payload["probe"]["path"] == "l0"
    assert payload["probe"]["ready"] is False
    imports = [c for c in payload["probe"]["checks"] if c["id"] == "host_import"]
    assert imports and imports[0]["status"] == "missing"
    assert imports[0]["hint"]


def test_l0_import_present_and_locator_ready(
    bora_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del bora_home
    _vendor_sdk(tmp_path, monkeypatch)
    payload, ready = build_probe_command().run(
        database_root=DB,
        task_id="l0-task",
        environ={"PROBE_API_KEY": SECRET},
    )
    assert ready is True
    assert payload["probe"]["ready"] is True
    blob = str(payload)
    assert SECRET not in blob
    loc = [c for c in payload["probe"]["checks"] if c["id"] == "credential_locator"]
    assert loc and loc[0]["ok"] is True
    assert loc[0]["present"] == ["PROBE_API_KEY"]


def test_l1_passes_without_host_import(bora_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del bora_home
    monkeypatch.delenv("PROBE_API_KEY", raising=False)
    payload, ready = build_probe_command().run(
        database_root=DB,
        task_id="l1-task",
        environ={"PROBE_API_KEY": "x"},
        docker_reachable=lambda: True,
    )
    assert ready is True
    assert payload["probe"]["path"] == "l1"
    ids = {c["id"] for c in payload["probe"]["checks"]}
    assert "host_import" not in ids
    assert "l1_contribute_selected" in ids
    assert "l1_bake_declared" in ids
    assert "docker_daemon" in ids
    selected = next(c for c in payload["probe"]["checks"] if c["id"] == "l1_contribute_selected")
    assert selected["ok"] is True
    bake = next(c for c in payload["probe"]["checks"] if c["id"] == "l1_bake_declared")
    assert bake["ok"] is True


def test_l1_executor_without_extensions_fails(bora_home: Path) -> None:
    del bora_home
    payload, ready = build_probe_command().run(
        database_root=DB,
        task_id="l1-task",
        profiles_path=DB / "profiles.no-ext.yaml",
        environ={"PROBE_API_KEY": "x"},
        docker_reachable=lambda: True,
    )
    assert ready is False
    selected = next(c for c in payload["probe"]["checks"] if c["id"] == "l1_contribute_selected")
    assert selected["ok"] is False
    bake = next(c for c in payload["probe"]["checks"] if c["id"] == "l1_bake_declared")
    assert bake["ok"] is False


def test_l1_docker_down_fails(bora_home: Path) -> None:
    del bora_home
    payload, ready = build_probe_command().run(
        database_root=DB,
        task_id="l1-task",
        environ={"PROBE_API_KEY": "x"},
        docker_reachable=lambda: False,
    )
    assert ready is False
    docker = next(c for c in payload["probe"]["checks"] if c["id"] == "docker_daemon")
    assert docker["ok"] is False


def test_probe_does_not_change_lock_digest(bora_home: Path) -> None:
    del bora_home
    locked = build_lock_command().run(database_root=DB, task_id="l0-task")
    probed, _ready = build_probe_command().run(
        database_root=DB,
        task_id="l0-task",
        environ={},
    )
    assert locked["digest"] == probed["digest"]
    assert "probe" not in locked
    assert "probe" in probed


def test_probe_reads_dataset_dotenv(
    bora_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del bora_home
    monkeypatch.delenv("PROBE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("PROBE_API_KEY=from-dotenv-secret\n", encoding="utf-8")
    link = DB / ".env"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(env_file)
    try:
        payload, _ready = build_probe_command().run(
            database_root=DB,
            task_id="l0-task",
        )
    finally:
        if link.exists() or link.is_symlink():
            link.unlink()
        monkeypatch.delenv("PROBE_API_KEY", raising=False)
    loc = [c for c in payload["probe"]["checks"] if c["id"] == "credential_locator"]
    assert loc and loc[0]["ok"] is True
    assert loc[0]["present"] == ["PROBE_API_KEY"]
    assert "from-dotenv-secret" not in str(payload)


def test_offline_is_reported(bora_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del bora_home
    monkeypatch.setenv("BORA_OFFLINE_AGENT", "1")
    payload, _ready = build_probe_command().run(
        database_root=DB,
        task_id="l0-task",
        environ={},
    )
    assert payload["probe"]["offline_agent"] is True


def test_probe_walks_extension_plugin_requires(
    bora_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bora.application.attempt.probe_command import probe_locked
    from bora.application.composition import build_lock_command
    from bora.plugins.install import install_from_local
    from bora.plugins.store import uninstall

    del bora_home
    monkeypatch.setenv("PROBE_API_KEY", "x")
    plugins = tmp_path / "plugins"
    for name in ("neighbor", "needs-neighbor"):
        root = plugins / name
        root.mkdir(parents=True)
        requires = "plugin_requires:\n  - plugin_id: neighbor\n" if name == "needs-neighbor" else ""
        (root / "plugin.yaml").write_text(
            (
                "format: bora.plugin/1\n"
                f"plugin_id: {name}\n"
                "version: 0.1.0\n"
                f"{requires}"
                "slots:\n"
                '  "on":\n'
                "    - id: home_overlay\n"
                "      priority: 120\n"
                "      entry: demo.hooks:build\n"
            ),
            encoding="utf-8",
        )
        src = root / "src" / "demo"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("", encoding="utf-8")
        (src / "hooks.py").write_text(
            "def build(**_k):\n    async def h(ctx, value, nxt):\n        return await nxt(value)\n    return h\n",
            encoding="utf-8",
        )
    install_from_local(plugins / "needs-neighbor")
    profiles = tmp_path / "profiles.yaml"
    profiles.write_text(
        (
            "format: bora.profiles/1\n"
            "bindings:\n"
            "  solver:\n"
            "    executor: host-probe\n"
            "    extensions:\n"
            "      - plugin: host-probe\n"
            "      - plugin: needs-neighbor\n"
            "    model: none\n"
            "    api_key: ${PROBE_API_KEY}\n"
        ),
        encoding="utf-8",
    )
    from bora.plugins import bootstrap as boot
    from bora.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    locked, _extra = build_lock_command().lock_with_provenance(
        database_root=DB,
        task_id="l0-task",
        profiles_path=profiles,
    )
    locked_l1, _ = build_lock_command().lock_with_provenance(
        database_root=DB,
        task_id="l1-task",
        profiles_path=profiles,
    )
    ok_probe = probe_locked(locked, environ={"PROBE_API_KEY": "x"})
    reqs = [c for c in ok_probe["checks"] if c["id"] == "plugin_requires"]
    assert reqs and all(c["ok"] for c in reqs)
    installed = [c for c in ok_probe["checks"] if c["id"] == "plugin_installed"]
    assert any(c["plugin"] == "needs-neighbor" and c["ok"] for c in installed)

    uninstall("neighbor")
    missing = probe_locked(locked, environ={"PROBE_API_KEY": "x"})
    assert missing["ready"] is False
    reqs = [c for c in missing["checks"] if c["id"] == "plugin_requires"]
    assert reqs and any(c["ok"] is False and c["required"] == "neighbor" for c in reqs)

    l1_probe = probe_locked(
        locked_l1,
        environ={"PROBE_API_KEY": "x"},
        docker_reachable=lambda: True,
    )
    assert l1_probe["path"] == "l1"
    assert l1_probe["ready"] is False
    assert any(c["id"] == "plugin_requires" and c["ok"] is False for c in l1_probe["checks"])
    assert "host_import" not in {c["id"] for c in l1_probe["checks"]}


def test_no_plugin_id_extra_table() -> None:
    text = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "bora"
        / "application"
        / "attempt"
        / "probe_command.py"
    ).read_text(encoding="utf-8")
    assert 'plugin_id == "dsh"' not in text
    assert 'if kind == "dsh"' not in text
    assert "deepseek-harness-sdk" not in text
