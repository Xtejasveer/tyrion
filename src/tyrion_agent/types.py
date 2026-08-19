"""Shared low-level types for Tyrion's portable agent layer."""

from __future__ import annotations

type JSONPrimitive = str |int| float | bool | None
type JSONValue = JSONPrimitive | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]
