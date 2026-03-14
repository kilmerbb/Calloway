"""Tests for app.tools.sql_utils — defense-in-depth column validation."""
import pytest

from app.tools.sql_utils import build_safe_update_clause


# --- Happy path ---

def test_basic_update():
    clause, vals = build_safe_update_clause(
        {"name": "Alice", "email": "a@b.com"},
        allowed={"name", "email", "phone"},
    )
    assert '"name" = %s' in clause
    assert '"email" = %s' in clause
    assert vals == ["Alice", "a@b.com"]


def test_filters_to_allowed_only():
    clause, vals = build_safe_update_clause(
        {"name": "Alice", "hacked": "bad"},
        allowed={"name"},
    )
    assert clause == '"name" = %s'
    assert vals == ["Alice"]


def test_none_values_skipped():
    clause, vals = build_safe_update_clause(
        {"name": None, "email": "a@b.com"},
        allowed={"name", "email"},
    )
    assert clause == '"email" = %s'
    assert vals == ["a@b.com"]


def test_empty_after_filtering():
    clause, vals = build_safe_update_clause(
        {"hacked": "bad"},
        allowed={"name"},
    )
    assert clause == ""
    assert vals == []


def test_all_none_returns_empty():
    clause, vals = build_safe_update_clause(
        {"name": None},
        allowed={"name"},
    )
    assert clause == ""
    assert vals == []


def test_column_names_double_quoted():
    clause, _ = build_safe_update_clause(
        {"lifecycle_stage": "active"},
        allowed={"lifecycle_stage"},
    )
    assert clause == '"lifecycle_stage" = %s'


# --- SQL injection payloads are rejected ---

def test_rejects_sql_injection_semicolon():
    """Column name with semicolon must not pass regex — raises ValueError."""
    with pytest.raises(ValueError, match="Invalid column name"):
        build_safe_update_clause(
            {"name; DROP TABLE contacts--": "x"},
            allowed={"name; DROP TABLE contacts--"},
        )


def test_rejects_sql_injection_quotes():
    with pytest.raises(ValueError, match="Invalid column name"):
        build_safe_update_clause(
            {"name' OR '1'='1": "x"},
            allowed={"name' OR '1'='1"},
        )


def test_rejects_parentheses():
    with pytest.raises(ValueError, match="Invalid column name"):
        build_safe_update_clause(
            {"name()": "x"},
            allowed={"name()"},
        )


def test_rejects_spaces():
    with pytest.raises(ValueError, match="Invalid column name"):
        build_safe_update_clause(
            {"name col": "x"},
            allowed={"name col"},
        )


def test_rejects_hyphen():
    with pytest.raises(ValueError, match="Invalid column name"):
        build_safe_update_clause(
            {"my-col": "x"},
            allowed={"my-col"},
        )


def test_rejects_uppercase():
    """Only lowercase identifiers are accepted."""
    with pytest.raises(ValueError, match="Invalid column name"):
        build_safe_update_clause(
            {"Name": "x"},
            allowed={"Name"},
        )


def test_rejects_leading_digit():
    with pytest.raises(ValueError, match="Invalid column name"):
        build_safe_update_clause(
            {"1col": "x"},
            allowed={"1col"},
        )


def test_injection_not_in_allowlist_silently_dropped():
    """If the injection payload isn't in the allowlist, it's just filtered out."""
    clause, vals = build_safe_update_clause(
        {"Robert'; DROP TABLE students--": "x"},
        allowed={"name", "email"},
    )
    assert clause == ""
    assert vals == []
