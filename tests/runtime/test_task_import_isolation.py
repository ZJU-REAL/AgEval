"""Task-dir import cleanup so suite tasks do not share lib.agents cache."""

from __future__ import annotations

import sys
from pathlib import Path

from ageval.runtime.task_import_isolation import clear_imports_from_task_dir


def test_clear_imports_allows_reload_of_same_module_name(tmp_path: Path) -> None:
    task_a = tmp_path / "task_a"
    task_b = tmp_path / "task_b"
    (task_a / "lib").mkdir(parents=True)
    (task_b / "lib").mkdir(parents=True)
    (task_a / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (task_b / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (task_a / "lib" / "agents.py").write_text("MARKER = 'a'\nclass OnlyA: pass\n", encoding="utf-8")
    (task_b / "lib" / "agents.py").write_text("MARKER = 'b'\nclass OnlyB: pass\n", encoding="utf-8")

    sys.path.insert(0, str(task_a))
    import lib.agents as agents_a  # type: ignore[import-not-found]

    assert agents_a.MARKER == "a"
    assert hasattr(agents_a, "OnlyA")
    assert not hasattr(agents_a, "OnlyB")

    clear_imports_from_task_dir(task_a)

    sys.path.insert(0, str(task_b))
    import lib.agents as agents_b  # type: ignore[import-not-found]

    assert agents_b.MARKER == "b"
    assert hasattr(agents_b, "OnlyB")
    assert not hasattr(agents_b, "OnlyA")

    clear_imports_from_task_dir(task_b)
