"""Shared SQL utilities for safe dynamic query construction."""
import re


def build_safe_update_clause(fields: dict, allowed: set[str]) -> tuple[str, list]:
    """Build a safe SET clause from validated field names.

    Double gate: allowlist filter + regex validation.
    Returns (set_clause, values) for use in UPDATE queries.

    Only fields present in `allowed` and passing the regex check are included.
    None values are silently skipped.
    """
    safe = {}
    for k, v in fields.items():
        if v is None:
            continue
        if k not in allowed:
            continue
        if not re.match(r'^[a-z_][a-z0-9_]*$', k):
            raise ValueError(f"Invalid column name: {k}")
        safe[k] = v
    if not safe:
        return "", []
    set_parts = [f'"{k}" = %s' for k in safe]
    return ", ".join(set_parts), list(safe.values())
