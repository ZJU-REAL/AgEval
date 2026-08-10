"""Campaign matrix expansion tests."""

from __future__ import annotations

import pytest

from bora.application.campaign import MatrixAxis, expand_matrix, parse_matrix_arg
from bora.config.errors import ConfigError


def test_expand_cartesian() -> None:
    axes = [
        MatrixAxis("/parameters/a", (1, 2)),
        MatrixAxis("/parameters/b", ("x",)),
    ]
    variants = expand_matrix(axes)
    assert len(variants) == 2
    assert variants[0]["/parameters/a"] == 1


def test_unsupported_pointer() -> None:
    with pytest.raises(ConfigError) as ei:
        parse_matrix_arg('/provider/kind=["docker"]')
    assert ei.value.error_code == "campaign_matrix_pointer_unsupported"


def test_parse_ok() -> None:
    axis = parse_matrix_arg("/parameters/seed=[1,2,3]")
    assert axis.values == (1, 2, 3)


def test_parse_binding_axis() -> None:
    axis = parse_matrix_arg('/bindings/solver/model=["a","b"]')
    assert axis.pointer == "/bindings/solver/model"
    assert axis.values == ("a", "b")
