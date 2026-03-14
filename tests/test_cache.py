"""Tests for app.services.cache — generic Redis caching layer."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.cache import (
    cache_get,
    cache_set,
    cache_invalidate,
    cache_invalidate_pattern,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Return a mock Redis client and patch get_redis_pool to return it."""
    client = MagicMock()
    with patch("app.services.cache.get_redis_pool", return_value=client):
        yield client


@pytest.fixture
def broken_redis():
    """Patch get_redis_pool to raise ConnectionError (simulates Redis down)."""
    with patch(
        "app.services.cache.get_redis_pool",
        side_effect=ConnectionError("Redis unavailable"),
    ):
        yield


# ---------------------------------------------------------------------------
# cache_get
# ---------------------------------------------------------------------------

class TestCacheGet:
    def test_returns_value_on_hit(self, mock_redis):
        mock_redis.get.return_value = b'{"hello": "world"}'
        assert cache_get("calloway:test:1") == b'{"hello": "world"}'
        mock_redis.get.assert_called_once_with("calloway:test:1")

    def test_returns_none_on_miss(self, mock_redis):
        mock_redis.get.return_value = None
        assert cache_get("calloway:test:missing") is None

    def test_returns_none_when_redis_unavailable(self, broken_redis):
        result = cache_get("calloway:test:1")
        assert result is None

    def test_returns_none_on_redis_error(self, mock_redis):
        mock_redis.get.side_effect = Exception("timeout")
        result = cache_get("calloway:test:1")
        assert result is None


# ---------------------------------------------------------------------------
# cache_set
# ---------------------------------------------------------------------------

class TestCacheSet:
    def test_sets_value_with_default_ttl(self, mock_redis):
        cache_set("calloway:test:1", b"data")
        mock_redis.setex.assert_called_once_with("calloway:test:1", 300, b"data")

    def test_sets_value_with_custom_ttl(self, mock_redis):
        cache_set("calloway:test:1", b"data", ttl=30)
        mock_redis.setex.assert_called_once_with("calloway:test:1", 30, b"data")

    def test_accepts_string_value(self, mock_redis):
        cache_set("calloway:test:1", '{"key": "val"}', ttl=60)
        mock_redis.setex.assert_called_once_with(
            "calloway:test:1", 60, '{"key": "val"}'
        )

    def test_silent_on_redis_unavailable(self, broken_redis):
        # Must not raise
        cache_set("calloway:test:1", b"data")

    def test_silent_on_redis_error(self, mock_redis):
        mock_redis.setex.side_effect = Exception("write error")
        # Must not raise
        cache_set("calloway:test:1", b"data")


# ---------------------------------------------------------------------------
# cache_invalidate
# ---------------------------------------------------------------------------

class TestCacheInvalidate:
    def test_deletes_key(self, mock_redis):
        cache_invalidate("calloway:test:1")
        mock_redis.delete.assert_called_once_with("calloway:test:1")

    def test_silent_on_redis_unavailable(self, broken_redis):
        cache_invalidate("calloway:test:1")

    def test_silent_on_redis_error(self, mock_redis):
        mock_redis.delete.side_effect = Exception("delete error")
        cache_invalidate("calloway:test:1")


# ---------------------------------------------------------------------------
# cache_invalidate_pattern
# ---------------------------------------------------------------------------

class TestCacheInvalidatePattern:
    def test_scans_and_deletes_matching_keys(self, mock_redis):
        # Simulate: first scan returns keys, second scan returns cursor=0
        mock_redis.scan.side_effect = [
            (42, [b"calloway:conv:a:1", b"calloway:conv:a:2"]),
            (0, [b"calloway:conv:a:3"]),
        ]
        cache_invalidate_pattern("calloway:conv:a:*")

        assert mock_redis.scan.call_count == 2
        mock_redis.delete.assert_any_call(
            b"calloway:conv:a:1", b"calloway:conv:a:2"
        )
        mock_redis.delete.assert_any_call(b"calloway:conv:a:3")

    def test_no_delete_when_no_keys(self, mock_redis):
        mock_redis.scan.return_value = (0, [])
        cache_invalidate_pattern("calloway:nope:*")
        mock_redis.delete.assert_not_called()

    def test_silent_on_redis_unavailable(self, broken_redis):
        cache_invalidate_pattern("calloway:*")

    def test_silent_on_redis_error(self, mock_redis):
        mock_redis.scan.side_effect = Exception("scan error")
        cache_invalidate_pattern("calloway:*")


# ---------------------------------------------------------------------------
# Integration-style: round-trip get/set/invalidate
# ---------------------------------------------------------------------------

class TestCacheRoundTrip:
    def test_set_then_get_returns_value(self, mock_redis):
        mock_redis.get.return_value = b"cached-data"

        cache_set("calloway:test:rt", b"cached-data", ttl=60)
        result = cache_get("calloway:test:rt")

        assert result == b"cached-data"
        mock_redis.setex.assert_called_once()
        mock_redis.get.assert_called_once()

    def test_invalidate_then_get_returns_none(self, mock_redis):
        mock_redis.get.return_value = None

        cache_invalidate("calloway:test:rt")
        result = cache_get("calloway:test:rt")

        assert result is None
