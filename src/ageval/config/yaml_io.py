"""YAML parse helpers for Config Core (unique keys, deep merge)."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import yaml

from ageval.config.errors import ERROR_INVALID_SCHEMA, ConfigError


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (YAML normally overwrites)."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)  # type: ignore[arg-type]
        if key in mapping:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"duplicate key in YAML mapping: {key!r}",
                location="task.yaml",
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)  # type: ignore[arg-type]
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,  # type: ignore[arg-type]
)


def parse_yaml(text: str) -> Any:
    """Parse task.yaml text; reject duplicate keys and non-mapping roots."""
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except ConfigError:
        raise
    except yaml.YAMLError as exc:
        raise ConfigError(
            ERROR_INVALID_SCHEMA, f"invalid YAML: {exc}", location="task.yaml"
        ) from exc
    if data is None:
        raise ConfigError(ERROR_INVALID_SCHEMA, "empty task.yaml", location="task.yaml")
    if not isinstance(data, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "task.yaml root must be a mapping",
            location="task.yaml",
        )
    return data


def deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-merge overlay onto base; mappings merge, other values replace."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            result[key] = deep_merge(existing, value)
        else:
            result[key] = copy.deepcopy(value)
    return result
