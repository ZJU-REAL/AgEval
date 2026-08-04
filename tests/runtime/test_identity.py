"""Identity factory and scope tests."""

from __future__ import annotations

import re

import pytest

from bora.runtime.errors import LifecycleError
from bora.runtime.identity import IdentityFactory


def test_default_prefixes() -> None:
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "a" * 64)
    attempt = factory.new_attempt(trial)
    assert run.value.startswith("run_")
    assert trial.value.startswith("trial_")
    assert attempt.value.startswith("attempt_")
    assert re.fullmatch(r"run_[0-9a-f]{32}", run.value)
    assert attempt.retry_of_attempt_id is None


def test_deterministic_source() -> None:
    counter = {"n": 0}

    def src() -> str:
        counter["n"] += 1
        return f"{counter['n']:032x}"

    factory = IdentityFactory(id_source=src)
    r1 = factory.new_run()
    r2 = factory.new_run()
    assert r1.value == "run_" + "0" * 31 + "1"
    assert r2.value != r1.value


def test_retry_same_trial() -> None:
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "b" * 64)
    first = factory.new_attempt(trial)
    second = factory.new_attempt(trial, retry_of=first)
    assert second.retry_of_attempt_id == first.value
    assert second.trial == trial
    assert second.value != first.value


def test_retry_cross_trial_rejected() -> None:
    factory = IdentityFactory()
    run = factory.new_run()
    t1 = factory.new_trial(run, "sha256:" + "c" * 64)
    t2 = factory.new_trial(run, "sha256:" + "d" * 64)
    a1 = factory.new_attempt(t1)
    with pytest.raises(LifecycleError) as ei:
        factory.new_attempt(t2, retry_of=a1)
    assert ei.value.error_code == "invalid_retry"


def test_trial_requires_digest() -> None:
    factory = IdentityFactory()
    run = factory.new_run()
    with pytest.raises(LifecycleError):
        factory.new_trial(run, "not-a-digest")
