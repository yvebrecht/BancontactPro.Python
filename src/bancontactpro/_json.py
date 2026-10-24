"""Wire-format mapping between snake_case dataclasses and Bancontact's camelCase JSON.

Unset optional fields are omitted from requests, never sent as null: the specs define them as optional, not
nullable, and an explicit null can be rejected.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


def to_camel(name: str) -> str:
    head, *rest = name.rstrip("_").split("_")
    return head + "".join(part.capitalize() for part in rest)


def _wire_name(name: str) -> str:
    # The spec's hypermedia property is literally "_links".
    return "_links" if name == "links" else to_camel(name)


def format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def to_json(value: Any) -> Any:
    """Converts a request dataclass (or nested value) to JSON-ready data, omitting None."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            _wire_name(f.name): to_json(getattr(value, f.name)) for f in dataclasses.fields(value) if getattr(value, f.name) is not None
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return format_datetime(value)
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    return value


def from_json(cls: type[T], data: Any) -> T:
    """Builds a response dataclass from decoded JSON. Unknown properties are ignored."""
    return _convert(cls, data)  # type: ignore[no-any-return]


def _convert(tp: Any, data: Any) -> Any:
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        if data is None:
            return None
        inner = [a for a in typing.get_args(tp) if a is not type(None)]
        return _convert(inner[0], data)
    if data is None:
        return None
    if origin in (list, tuple):
        item = typing.get_args(tp)[0]
        return [_convert(item, element) for element in data]
    if isinstance(tp, type):
        if dataclasses.is_dataclass(tp):
            hints = typing.get_type_hints(tp)
            kwargs = {}
            for f in dataclasses.fields(tp):
                wire = _wire_name(f.name)
                if wire in data:
                    kwargs[f.name] = _convert(hints[f.name], data[wire])
                elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                    raise ValueError(f"Missing required property '{wire}' for {tp.__name__}.")
            return tp(**kwargs)
        if issubclass(tp, Enum):
            return tp(data)
        if tp is datetime:
            return parse_datetime(data)
    return data
