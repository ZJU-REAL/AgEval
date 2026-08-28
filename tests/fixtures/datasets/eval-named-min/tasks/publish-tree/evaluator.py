"""Score inside the audit box. The unused named host must not start."""

from __future__ import annotations

from typing import Any


async def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    scoring = inputs["scoring"]
    inside = await scoring.exec(
        "audit",
        [
            "python",
            "-c",
            "print(open('/attempt/workspace/answer.txt').read().strip()); "
            "print(open('/attempt/evaluation/expected.txt').read().strip()); "
            "import os; print(os.path.exists('/attempt/workspace/target/leak.so'))",
        ],
    )
    lines = [line.strip() for line in inside.stdout.splitlines() if line.strip()]
    answer = lines[0] if lines else ""
    expected = lines[1] if len(lines) > 1 else ""
    leaked = lines[2] == "True" if len(lines) > 2 else True
    ok = inside.exit_code == 0 and answer == "42" and expected == "42" and not leaked
    return {
        "status": "PASS" if ok else "FAIL",
        "score": 1.0 if ok else 0.0,
        "metrics": {
            "answer": answer,
            "expected": expected,
            "leaked": leaked,
            "exit_code": inside.exit_code,
        },
    }
