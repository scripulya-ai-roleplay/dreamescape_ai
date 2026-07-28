from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.models import ChatRoles, Message
from src.infrastructure.gateways.openai_summary_model import OpenAISummaryModel


@pytest.mark.unit
@pytest.mark.asyncio
async def test_summarize_returns_model_content_and_threads_prior():
	client = AsyncMock()
	client.chat.completions.create = AsyncMock(
		return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" combined summary "))])
	)
	model = OpenAISummaryModel(_client=client, _model="gpt-4o-mini")

	messages = [
		Message(id=uuid4(), message="hello there", chat_id=uuid4(), role=ChatRoles.USER),
		Message(id=uuid4(), message="general kenobi", chat_id=uuid4(), role=ChatRoles.MODEL),
	]
	result = await model.summarize("prior summary", messages)

	assert result == "combined summary"
	create_kwargs = client.chat.completions.create.await_args.kwargs
	assert create_kwargs["model"] == "gpt-4o-mini"
	user_content = create_kwargs["messages"][1]["content"]
	assert "prior summary" in user_content
	assert "hello there" in user_content
