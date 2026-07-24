import asyncio
from uuid import uuid4

import pytest

from src.infrastructure.gateways.chat_event_gateway import ChatEventGateway


@pytest.mark.unit
class TestChatEventGatewayTokenFanout:
	@pytest.mark.asyncio
	async def test_publish_token_fans_out_to_all_listeners_tagged(self):
		gateway = ChatEventGateway()
		chat_id = uuid4()
		request_id = uuid4()
		q1 = gateway.subscribe(chat_id)
		q2 = gateway.subscribe(chat_id)

		gateway.publish_token(chat_id, request_id, "hi")

		e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
		e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
		assert e1 == e2 == {"_sse_event": "token", "request_id": str(request_id), "text": "hi"}

		gateway.unsubscribe(chat_id, q1)
		gateway.unsubscribe(chat_id, q2)

	@pytest.mark.asyncio
	async def test_generation_start_and_done_are_tagged(self):
		gateway = ChatEventGateway()
		chat_id = uuid4()
		request_id = uuid4()
		q = gateway.subscribe(chat_id)

		gateway.publish_generation_start(chat_id, request_id)
		gateway.publish_generation_done(chat_id, request_id)

		start = await asyncio.wait_for(q.get(), timeout=1.0)
		done = await asyncio.wait_for(q.get(), timeout=1.0)
		assert start["_sse_event"] == "generation_start"
		assert done["_sse_event"] == "generation_done"
		assert start["request_id"] == done["request_id"] == str(request_id)

		gateway.unsubscribe(chat_id, q)

	@pytest.mark.asyncio
	async def test_no_listeners_is_silent_noop(self):
		gateway = ChatEventGateway()
		gateway.publish_token(uuid4(), uuid4(), "orphan")
