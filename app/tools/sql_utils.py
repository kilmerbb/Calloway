"""Shared SQL utilities for safe dynamic query construction."""
import re


def escape_ilike(value: str) -> str:
    """Escape ILIKE wildcard characters in user-supplied search values.

    Parameterization prevents SQL injection but does not escape LIKE/ILIKE
    wildcards (% and _). Without escaping, a user could submit '%' to match
    all rows or '_' for single-character wildcards.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
