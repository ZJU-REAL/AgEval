"""One Run/Trial/Attempt identity per production Attempt (Wave 1a)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.doubles.lifecycle_stages import ScriptedLifecycleStages

from bora.adapters.provider_docker.types import DockerImageLock, DockerRuntime
from bora.application.attempt.run_command import run_task
from bora.application.attempt.run_l1_prepare import prepare_l1_runtime
from bora.application.attempt.run_lifecycle import run_lifecycle
from bora.runtime.identity import IdentityFactory

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "examples" / "core"


class CountingFactory(IdentityFactory):
    def __init__(self) -> None:
        super().__init__()
        self.new_run_calls = 0

    def new_run(self):  # type: ignore[override]
        self.new_run_calls += 1
        return super().new_run()


def _attempt(digest: str = "sha256:" + "a" * 64):
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, digest)
    return factory.new_attempt(trial)


@pytest.mark.asyncio
async def test_run_lifecycle_uses_passed_attempt() -> None:
    from bora.adapters.package_fs import LocalPackageReader
    from bora.config.capabilities import DeclarationCapabilityCatalog
    from bora.config.load_and_lock import ConfigCore
    from bora.config.profiles import load_database_profiles

    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        CORE / "tasks" / "config-minimal",
        "config-minimal",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=load_database_profiles(CORE),
    )
    attempt = _attempt(lock.digest)
    record = await run_lifecycle(lock, ScriptedLifecycleStages(), attempt=attempt)
    assert record.attempt is attempt


@pytest.mark.asyncio
async def test_l0_run_dir_suffix_matches_evidence_run_id(tmp_path: Path) -> None:
    _code, _flat, details = await run_task(
        CORE,
        "sdk-agent-session",
        evidence_root=tmp_path / "runs",
        allow_offline_agent=True,
    )
    runs = [p for p in (tmp_path / "runs").iterdir() if p.is_dir()]
    assert len(runs) == 1
    run_dir = runs[0]
    agent = json.loads((run_dir / "agent.json").read_text(encoding="utf-8"))
    run_id = str(agent["run_id"])
    digest = str(details["digest"])
    assert run_dir.name.endswith(run_id[:16])
    assert run_dir.name.startswith(digest.replace(":", "_")[:48])


@pytest.mark.asyncio
async def test_run_task_mints_one_run_identity(tmp_path: Path) -> None:
    factory = CountingFactory()
    await run_task(
        CORE,
        "sdk-agent-session",
        evidence_root=tmp_path / "runs",
        allow_offline_agent=True,
        identity_factory=factory,
    )
    assert factory.new_run_calls == 1


def test_prepare_l1_runtime_uses_passed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bora.application.attempt.extension_hooks as hooks
    import bora.application.attempt.run_l1_prepare as prep
    import bora.application.plugin_ops.image_contribute_bake as bake

    attempt = _attempt()
    image = DockerImageLock(
        kind="attempt",
        platform="linux/arm64",
        image_tag="bora-pkg:t-dead",
        image_digest="sha256:abc",
        build_input_digest="sha256:def",
    )
    seen: dict[str, object] = {}

    class FakeDocker:
        def __init__(self, *, image_lock_path: Path) -> None:
            self.image_lock_path = image_lock_path

        def prepare(self, got_attempt, **_kwargs):  # type: ignore[no-untyped-def]
            seen["attempt"] = got_attempt
            return DockerRuntime(
                attempt=got_attempt,
                image_lock=image,
                workdir_host=tmp_path / "work",
            )

    monkeypatch.setattr(prep, "ensure_base_image", lambda _cwd: None)
    monkeypatch.setattr(prep, "build_package_image", lambda **_kw: image)
    monkeypatch.setattr(prep, "ensure_image_lock", lambda _cwd: tmp_path / "lock.json")
    monkeypatch.setattr(prep, "DockerProvider", FakeDocker)
    monkeypatch.setattr(hooks, "hook_prepare", lambda *_a, **_k: None)
    monkeypatch.setattr(bake, "apply_image_contribute_bake", lambda **_kw: (image, {"ok": True}))

    lock = SimpleNamespace(
        digest="sha256:" + "b" * 64,
        task_id="sample",
        provider={"kind": "docker", "dockerfile": "environment/Dockerfile"},
    )
    _docker, runtime, meta = prepare_l1_runtime(
        tmp_path,
        lock,
        tmp_path / "run",
        attempt=attempt,
    )
    assert seen["attempt"] is attempt
    assert runtime.attempt is attempt
    assert meta["attempt_id"] == attempt.value


def test_l1_prepare_source_has_no_identity_factory() -> None:
    src = inspect.getsource(prepare_l1_runtime)
    assert "IdentityFactory" not in src
    module_src = Path(inspect.getfile(prepare_l1_runtime)).read_text(encoding="utf-8")
    assert "IdentityFactory" not in module_src
