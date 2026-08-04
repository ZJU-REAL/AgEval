"""L1 credential projection must not dump secrets into evidence JSON."""

from __future__ import annotations

import json
from pathlib import Path

from bora.adapters.credential_projection import project_executor_credentials


def test_projection_locator_has_no_raw_secret_in_keys_list(tmp_path: Path) -> None:
    proj = project_executor_credentials(work_root=tmp_path)
    try:
        blob = json.dumps({"keys": proj.locator_keys})
        assert "sk-" not in blob
        # locator keys are path names only
        for k in proj.locator_keys:
            assert not k.startswith("sk-")
        # Scoped home for container — never host tree mount marker
        assert (proj.root / "home").is_dir()
        assert "home/" in proj.locator_keys
    finally:
        proj.cleanup()
