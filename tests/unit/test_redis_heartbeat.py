from collections import defaultdict
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from src.infrastructure.gateways.redis_heartbeat import (
	RedisGenerationHeartbeat,
	_alive_key,
	_chat_key,
	_done_key,
)


class _FakeRedis:
	"""In-memory stand-in for redis.asyncio.Redis covering the ops the heartbeat uses
	(strings, sets, SET NX, pipeline). TTLs are ignored — expiry is tested by
	removing keys, which is what an expired TTL amounts to from the client's view."""

	def __init__(self):
		self._strings: dict[str, str] = {}
		self._sets: dict[str, set[str]] = defaultdict(set)

	def pipeline(self, transaction=True):
		return _FakePipe(self)

	async def smembers(self, key):
		return set(self._sets.get(key, set()))

	async def exists(self, key):
		return int(key in self._strings)

	async def get(self, key):
		return self._strings.get(key)

	async def set(self, key, value, ex=None, nx=False):  # noqa: ARG002
		if nx and key in self._strings:
			return False
		self._strings[key] = value
		return True

	async def sadd(self, key, *members):
		before = len(self._sets[key])
		self._sets[key].update(members)
		return len(self._sets[key]) - before

	async def srem(self, key, *members):
		s = self._sets.setdefault(key, set())
		removed = 0
		for m in members:
			if m in s:
				s.discard(m)
				removed += 1
		return removed


class _FakePipe:
	def __init__(self, fake: _FakeRedis):
		self._fake = fake
		self._cmds: list = []

	def sadd(self, key, *members):
		self._cmds.append(("sadd", key, members))
		return self

	def set(self, key, value, ex=None, nx=False):
		self._cmds.append(("set", key, value, ex, nx))
		return self

	async def execute(self):
		for cmd in self._cmds:
			if cmd[0] == "sadd":
				await self._fake.sadd(cmd[1], *cmd[2])
			elif cmd[0] == "set":
				await self._fake.set(cmd[1], cmd[2], ex=cmd[3], nx=cmd[4])
		self._cmds.clear()


def _heartbeat(redis=None):
	return RedisGenerationHeartbeat(_redis=redis or _FakeRedis(), logger=MagicMock())


@pytest.mark.unit
class TestRegisterInflight:
	@pytest.mark.asyncio
	async def test_writes_inflight_chat_and_alive_keys(self):
		fake = _FakeRedis()
		hb = _heartbeat(fake)
		rid, chat_id = "rid-1", uuid4()

		await hb.register_inflight(rid, chat_id)

		assert rid in await fake.smembers("gen:inflight")
		assert await fake.get(_chat_key(rid)) == str(chat_id)
		assert await fake.exists(_alive_key(rid)) == 1

	@pytest.mark.asyncio
	async def test_swallows_redis_errors(self):
		fake = _FakeRedis()
		fake.pipeline = MagicMock(side_effect=RuntimeError("redis down"))
		hb = _heartbeat(fake)

		await hb.register_inflight("rid-2", uuid4())  # must not raise


@pytest.mark.unit
class TestSweepDead:
	def _seed(self, fake: _FakeRedis, rids: dict[str, str | None], alive=None, done=None):
		"""rids: {request_id: chat_id_or_None}. alive/done: sets of request_ids."""
		alive = alive or set()
		done = done or set()
		for rid, chat in rids.items():
			fake._sets["gen:inflight"].add(rid)
			if chat is not None:
				fake._strings[_chat_key(rid)] = chat
			if rid in alive:
				fake._strings[_alive_key(rid)] = "1"
			if rid in done:
				fake._strings[_done_key(rid)] = "agent"

	@pytest.mark.asyncio
	async def test_returns_only_dead_and_drains_resolved(self):
		fake = _FakeRedis()
		alive_rid, done_rid, dead_rid = "alive", "done", "dead"
		dead_chat = str(uuid4())
		self._seed(
			fake,
			{alive_rid: str(uuid4()), done_rid: str(uuid4()), dead_rid: dead_chat},
			alive={alive_rid},
			done={done_rid},
		)
		hb = _heartbeat(fake)

		dead = await hb.sweep_dead()

		assert dead == [(dead_rid, UUID(dead_chat))]
		# alive left alone; done + dead drained from the inflight set
		inflight = await fake.smembers("gen:inflight")
		assert alive_rid in inflight
		assert done_rid not in inflight
		assert dead_rid not in inflight
		# the dead request is now marked done so it can't be re-FAILed
		assert await fake.exists(_done_key(dead_rid)) == 1

	@pytest.mark.asyncio
	async def test_claim_is_idempotent(self):
		fake = _FakeRedis()
		dead_rid = "dead"
		self._seed(fake, {dead_rid: str(uuid4())})
		hb = _heartbeat(fake)

		first = await hb.sweep_dead()
		second = await hb.sweep_dead()

		assert len(first) == 1
		assert second == []  # already claimed via the done marker

	@pytest.mark.asyncio
	async def test_swallows_redis_errors(self):
		fake = _FakeRedis()
		fake.smembers = MagicMock(side_effect=RuntimeError("redis down"))
		hb = _heartbeat(fake)

		assert await hb.sweep_dead() == []
