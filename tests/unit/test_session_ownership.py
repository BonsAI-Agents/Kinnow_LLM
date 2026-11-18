"""Session history is namespaced by the API key that owns it (serve/redis_client.py)."""

from serve import redis_client


class TestSessionOwnership:
    async def test_owners_have_separate_histories_for_the_same_session_id(self, fake_redis):
        await redis_client.session_set("s1", [{"role": "user", "content": "A"}], owner="alice")
        await redis_client.session_set("s1", [{"role": "user", "content": "B"}], owner="bob")
        assert (await redis_client.session_get("s1", "alice"))[0]["content"] == "A"
        assert (await redis_client.session_get("s1", "bob"))[0]["content"] == "B"

    async def test_an_owner_cannot_see_another_owners_or_an_unowned_session(self, fake_redis):
        await redis_client.session_set("s1", [{"role": "user", "content": "A"}], owner="alice")
        assert await redis_client.session_get("s1", "bob") == []
        assert await redis_client.session_get("s1") == []

    async def test_keys_carry_the_owner_prefix(self, fake_redis):
        await redis_client.session_set("s1", [], owner="alice")
        assert "session:alice:s1" in fake_redis.store

    async def test_unowned_sessions_keep_the_plain_key(self, fake_redis):
        await redis_client.session_set("s1", [])
        assert "session:s1" in fake_redis.store
