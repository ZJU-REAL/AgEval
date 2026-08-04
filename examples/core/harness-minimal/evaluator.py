"""Evaluator sentinel — must not run in v0.5."""


def evaluate(inputs: object) -> dict[str, object]:
    raise RuntimeError("evaluator must not run in v0.5 harness checkpoint")
