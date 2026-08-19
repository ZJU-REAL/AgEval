"""Clear task-scoped Python imports after an Attempt (suite host isolation).

Parent long-process suite runs multiple tasks in one process. Package-local
modules often share names (e.g. ``lib.agents``). After each task, drop modules
whose ``__file__`` lives under that task directory so the next task reloads
from disk.

Does **not** clear first-party / site-packages / Database ``shared/`` imports
unless those files live under the task dir.
"""

from __future__ import annotations

import sys
from pathlib import Path


def clear_imports_from_task_dir(task_dir: Path) -> None:
    """Remove ``sys.modules`` entries loaded from *task_dir* and drop path injects.

    Safe to call multiple times. Never calls ``sys.modules.clear()``.
    """
    try:
        root = task_dir.resolve(strict=False)
    except OSError:
        return
    if not root.parts:
        return

    to_drop: list[str] = []
    for name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        file_attr = getattr(mod, "__file__", None)
        if not file_attr or not isinstance(file_attr, str):
            continue
        try:
            path = Path(file_attr).resolve(strict=False)
        except OSError:
            continue
        try:
            path.relative_to(root)
        except ValueError:
            continue
        to_drop.append(name)

    # Longer names first so submodules go before parent packages.
    for name in sorted(to_drop, key=len, reverse=True):
        sys.modules.pop(name, None)

    root_s = str(root)
    # Also drop trailing-sep variants and any path equal to task_dir.
    cleaned: list[str] = []
    for entry in sys.path:
        if not entry:
            cleaned.append(entry)
            continue
        try:
            ep = Path(entry).resolve(strict=False)
        except OSError:
            cleaned.append(entry)
            continue
        if ep == root:
            continue
        cleaned.append(entry)
    if cleaned != sys.path:
        sys.path[:] = cleaned
    # Defensive: remove string equality hits left by non-resolvable paths.
    while root_s in sys.path:
        sys.path.remove(root_s)
