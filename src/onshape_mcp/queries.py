"""FeatureScript helpers: response unwrapping (M1) and query codegen (M3).

FeatureScript eval responses are deeply nested BTFSValue trees where every
node is {"btType": "...BTFSValueX", "message": {...fields...}}. unwrap_fs_value
collapses them into plain Python values:

- BTFSValueMap / map entries        -> dict
- BTFSValueArray                    -> list
- BTFSValueNumber/String/Boolean    -> number / str / bool
- BTFSValueWithUnits                -> number (OnShape internals are meters/
                                       radians; unit metadata is dropped)
- BTFSValueUndefined                -> None
- unknown node types                -> {"btType": ..., **unwrapped message}
"""

from __future__ import annotations

from typing import Any


def unwrap_fs_value(node: Any) -> Any:
    if node is None or isinstance(node, (str, int, float, bool)):
        return node
    if isinstance(node, list):
        return [unwrap_fs_value(item) for item in node]
    if not isinstance(node, dict):
        return node

    bt_type = node.get("btType", "")
    payload = node.get("message")
    if not isinstance(payload, dict):
        payload = {k: v for k, v in node.items() if k != "btType"}

    if "BTFSValueMap" in bt_type and "MapEntry" not in bt_type:
        entries = payload.get("value") or []
        result: dict[str, Any] = {}
        for entry in entries:
            entry_payload = entry.get("message", entry) if isinstance(entry, dict) else {}
            key = unwrap_fs_value(entry_payload.get("key"))
            value = unwrap_fs_value(entry_payload.get("value"))
            result[key if isinstance(key, str) else repr(key)] = value
        return result

    if "BTFSValueArray" in bt_type:
        return [unwrap_fs_value(item) for item in payload.get("value") or []]

    if "BTFSValueUndefined" in bt_type:
        return None

    if "BTFSValueWithUnits" in bt_type:
        return unwrap_fs_value(payload.get("value"))

    for marker in ("BTFSValueNumber", "BTFSValueString", "BTFSValueBoolean"):
        if marker in bt_type:
            return unwrap_fs_value(payload.get("value"))

    if "BTFSValue" in bt_type and "value" in payload:
        return unwrap_fs_value(payload["value"])

    # Unknown node (queries, transient ids, etc.): keep btType for context and
    # unwrap the fields we can.
    unwrapped = {key: unwrap_fs_value(value) for key, value in payload.items()}
    if bt_type:
        unwrapped["btType"] = bt_type
    return unwrapped
