"""Unit tests for serve/auth.py (API-key authentication, plan sections 11a and 19b)."""

import pytest
from fastapi import HTTPException

from serve import auth
from tests.conftest import TEST_API_KEY


class TestLoadApiKeys:
    def test_loads_the_primary_key(self):
        assert auth.load_api_keys() == 1

    def test_fails_loudly_when_no_key_is_configured(self, monkeypatch):
        monkeypatch.delenv("API_KEY_PROD")
        with pytest.raises(RuntimeError, match="API_KEY_PROD"):
            auth.load_api_keys()

    def test_blank_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("API_KEY_PROD", "   ")
        with pytest.raises(RuntimeError):
            auth.load_api_keys()

    def test_rotation_key_is_accepted_alongside_the_primary(self, monkeypatch):
        monkeypatch.setenv("API_KEY_NEW", "the-next-key")
        assert auth.load_api_keys() == 2

    def test_same_key_twice_is_loaded_once(self, monkeypatch):
        monkeypatch.setenv("API_KEY_NEW", TEST_API_KEY)
        assert auth.load_api_keys() == 1

    def test_production_rejects_short_keys(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        with pytest.raises(RuntimeError, match="at least"):
            auth.load_api_keys()

    def test_production_accepts_long_keys(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("API_KEY_PROD", "k" * 32)
        assert auth.load_api_keys() == 1

    def test_reloading_replaces_the_old_keys(self, monkeypatch):
        auth.load_api_keys()
        monkeypatch.setenv("API_KEY_PROD", "a-different-key")
        auth.load_api_keys()
        assert list(auth._owners) == ["a-different-key"]


class TestOwnerId:
    def test_is_stable_and_does_not_contain_the_key(self):
        assert auth.owner_id("secret-key") == auth.owner_id("secret-key")
        assert "secret" not in auth.owner_id("secret-key")

    def test_different_keys_get_different_owners(self):
        assert auth.owner_id("key-a") != auth.owner_id("key-b")


class TestRequireApiKey:
    @pytest.fixture(autouse=True)
    def _keys(self):
        auth.load_api_keys()

    async def test_valid_key_returns_the_owner_id(self):
        assert await auth.require_api_key(f"Bearer {TEST_API_KEY}") == auth.owner_id(TEST_API_KEY)

    async def test_surrounding_whitespace_in_the_token_is_ignored(self):
        assert await auth.require_api_key(f"Bearer   {TEST_API_KEY}  ") == auth.owner_id(TEST_API_KEY)

    @pytest.mark.parametrize("header", [
        None, "", TEST_API_KEY, f"Basic {TEST_API_KEY}", f"bearer {TEST_API_KEY}", "Bearer",
    ])
    async def test_missing_or_malformed_header_is_401(self, header):
        with pytest.raises(HTTPException) as exc:
            await auth.require_api_key(header)
        assert exc.value.status_code == 401
        assert exc.value.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.parametrize("token", ["wrong", TEST_API_KEY + "x", TEST_API_KEY[:-1], ""])
    async def test_wrong_key_is_401(self, token):
        with pytest.raises(HTTPException) as exc:
            await auth.require_api_key(f"Bearer {token}")
        assert exc.value.status_code == 401

    async def test_both_keys_work_during_rotation(self, monkeypatch):
        monkeypatch.setenv("API_KEY_NEW", "the-next-key")
        auth.load_api_keys()
        old = await auth.require_api_key(f"Bearer {TEST_API_KEY}")
        new = await auth.require_api_key("Bearer the-next-key")
        assert old != new

    async def test_retired_key_stops_working_after_rotation(self, monkeypatch):
        monkeypatch.setenv("API_KEY_PROD", "the-next-key")
        auth.load_api_keys()
        with pytest.raises(HTTPException) as exc:
            await auth.require_api_key(f"Bearer {TEST_API_KEY}")
        assert exc.value.status_code == 401

    async def test_unconfigured_authentication_refuses_with_503_not_open_access(self):
        auth._owners.clear()
        with pytest.raises(HTTPException) as exc:
            await auth.require_api_key(f"Bearer {TEST_API_KEY}")
        assert exc.value.status_code == 503
