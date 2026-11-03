from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.application.auth.authz import AuthorizationService
from src.application.ports.characters import ICharacterGateway
from src.application.ports.chats import IChatEventGateway, IChatGateway
from src.application.ports.common import IUnitOfWork
from src.application.ports.llm import ITokenCounter, LLMErrorResponse, LLMModelType
from src.application.ports.summarization import (
	ISummarizationAgentGateway,
	ISummaryRepository,
	SummaryRequest,
	SummaryResult,
	SummarySourceMessage,
)
from src.application.summarization.schemas import ChapterRange, CreateSummariesDTO, UpdateSummaryDTO
from src.application.summarization.service import SUMMARY_CHAT_SETTINGS, SummarizationService
from src.domain.models import Character, Chat, ChatRoles, ChatSummary, MessageStatus, SummaryStatus
from src.infrastructure.exceptions import (
	ChatReadOnlyException,
	LLMGatewayException,
	SummaryChapterStaleException,
	SummaryNotEditableException,
)
from src.infrastructure.gateways.summarization_agent_gateway import MockSummarizationGateway

BASE = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class _LengthCounter(ITokenCounter):
	def count(self, text: str) -> int:
		return len(text)


def _source(index, text, role=ChatRoles.USER):
	return SummarySourceMessage(
		id=uuid4(),
		role=role,
		content=text,
		status=MessageStatus.COMPLETED,
		created_at=BASE + timedelta(minutes=index),
	)


def _summary(chat_id, status=SummaryStatus.PENDING, model=LLMModelType.claude_sonnet, **overrides):
	values = {
		"id": uuid4(),
		"chat_id": chat_id,
		"status": status,
		"llm_model": model.value,
		"covered_from_at": BASE,
		"covered_until_at": BASE + timedelta(minutes=1),
		"messages_count": 2,
		"source_tokens": 4000,
	}
	values.update(overrides)
	return ChatSummary(**values)


@pytest.mark.unit
class TestSummarizationService:
	@pytest.fixture
	def owner_id(self):
		return uuid4()

	@pytest.fixture
	def chat(self, owner_id):
		return Chat(id=uuid4(), title="t", user_id=owner_id, scene_id=uuid4(), user_character_id=uuid4())

	@pytest.fixture
	def repository(self):
		repository = AsyncMock(spec=ISummaryRepository)
		repository.expire_pending.return_value = []
		repository.dispatch_next_queued.return_value = None
		repository.list_for_chat.return_value = []
		return repository

	@pytest.fixture
	def agent_gateway(self):
		gateway = AsyncMock(spec=ISummarizationAgentGateway)
		gateway.submit.return_value = None
		return gateway

	@pytest.fixture
	def chat_gateway(self, chat):
		gateway = AsyncMock(spec=IChatGateway)
		gateway.get_one.return_value = chat
		return gateway

	@pytest.fixture
	def character_gateway(self):
		gateway = AsyncMock(spec=ICharacterGateway)
		gateway.get_one.return_value = Character(name="Arin", system_prompt="hero")
		return gateway

	@pytest.fixture
	def events(self):
		return Mock(spec=IChatEventGateway)

	@pytest.fixture
	def uow(self):
		uow = AsyncMock(spec=IUnitOfWork)
		uow.__aenter__ = AsyncMock()
		uow.__aexit__ = AsyncMock(return_value=False)
		return uow

	@pytest.fixture
	def service(self, repository, agent_gateway, chat_gateway, character_gateway, events, uow):
		return SummarizationService(
			repository=repository,
			agent_gateway=agent_gateway,
			mock_gateway=MockSummarizationGateway(logger=Mock()),
			chat_gateway=chat_gateway,
			character_gateway=character_gateway,
			token_counter=_LengthCounter(),
			authz=AuthorizationService(),
			events=events,
			uow=uow,
			chunk_tokens=50,
			target_ratio=0.25,
			min_target_tokens=10,
			pending_timeout_seconds=600,
		)

	@pytest.fixture
	def messages(self):
		return [
			_source(0, "The gate creaks.", ChatRoles.MODEL),
			_source(1, "I step in."),
			_source(2, "A guard appears.", ChatRoles.MODEL),
		]

	@pytest.mark.asyncio
	async def test_list_chapters_counts_formatted_lines(self, service, repository, messages, chat, owner_id):
		repository.list_source_messages.return_value = messages

		chapters = await service.list_chapters(chat.id, owner_id)

		assert [c.messages_count for c in chapters] == [2, 1]
		assert chapters[0].tokens_count == len("Narrator: The gate creaks.") + len("Arin: I step in.")
		assert chapters[0].from_message_id == messages[0].id
		assert chapters[1].until_message_id == messages[2].id
		repository.expire_pending.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_list_chapters_rejects_foreign_chat(self, service, chat):
		with pytest.raises(HTTPException) as exc:
			await service.list_chapters(chat.id, uuid4())

		assert exc.value.status_code == 403

	@pytest.mark.asyncio
	async def test_summarize_queues_claims_and_dispatches(
		self, service, repository, agent_gateway, messages, chat, owner_id, events
	):
		repository.list_source_messages.return_value = messages
		created = _summary(chat.id, status=SummaryStatus.QUEUED)
		repository.create.return_value = created
		repository.claim_messages.return_value = 2
		dispatched = created.model_copy(update={"status": SummaryStatus.PENDING})
		repository.dispatch_next_queued.side_effect = [dispatched]
		repository.list_summary_messages.return_value = messages[:2]
		repository.get_one.return_value = dispatched

		result = await service.summarize(
			CreateSummariesDTO(
				chat_id=chat.id,
				llm_model=LLMModelType.claude_sonnet,
				chapters=[ChapterRange(from_message_id=messages[0].id, until_message_id=messages[1].id)],
			),
			owner_id,
		)

		assert result == [dispatched]
		new_summary = repository.create.await_args.args[0]
		assert new_summary.status == SummaryStatus.QUEUED
		assert new_summary.llm_model == LLMModelType.claude_sonnet.value
		assert new_summary.messages_count == 2
		assert new_summary.covered_until_at == messages[1].created_at
		repository.claim_messages.assert_awaited_once_with(created.id, [messages[0].id, messages[1].id])
		request: SummaryRequest = agent_gateway.submit.await_args.args[0]
		assert request.summary_id == created.id
		assert request.llm_model == LLMModelType.claude_sonnet
		assert request.chat_settings == SUMMARY_CHAT_SETTINGS
		assert "Arin" in request.system_prompt
		assert "Narrator: The gate creaks.\n\nArin: I step in." in request.content
		assert "<previous_summary>" not in request.content
		events.publish_summary.assert_called_once_with(chat.id, dispatched)

	@pytest.mark.asyncio
	async def test_request_carries_previous_completed_summary(self, service, repository, agent_gateway, chat, messages):
		earlier = _summary(
			chat.id,
			status=SummaryStatus.COMPLETED,
			content="They met at the gate.",
			covered_from_at=BASE - timedelta(hours=2),
			covered_until_at=BASE - timedelta(hours=1),
		)
		later = _summary(
			chat.id,
			status=SummaryStatus.COMPLETED,
			content="Later things.",
			covered_from_at=BASE + timedelta(hours=5),
			covered_until_at=BASE + timedelta(hours=6),
		)
		pending = _summary(chat.id)
		repository.list_for_chat.return_value = [earlier, later]
		repository.dispatch_next_queued.side_effect = [pending]
		repository.list_summary_messages.return_value = messages

		await service._pump(chat.id)

		request: SummaryRequest = agent_gateway.submit.await_args.args[0]
		assert "They met at the gate." in request.content
		assert "Later things." not in request.content

	@pytest.mark.asyncio
	async def test_summarize_unknown_range_is_stale(self, service, repository, messages, chat, owner_id):
		repository.list_source_messages.return_value = messages

		with pytest.raises(SummaryChapterStaleException):
			await service.summarize(
				CreateSummariesDTO(
					chat_id=chat.id,
					llm_model=LLMModelType.claude_sonnet,
					chapters=[ChapterRange(from_message_id=messages[0].id, until_message_id=messages[2].id)],
				),
				owner_id,
			)

		repository.create.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_summarize_lost_claim_race_is_stale(
		self, service, repository, messages, chat, owner_id, agent_gateway
	):
		repository.list_source_messages.return_value = messages
		repository.create.return_value = _summary(chat.id, status=SummaryStatus.QUEUED)
		repository.claim_messages.return_value = 1

		with pytest.raises(SummaryChapterStaleException):
			await service.summarize(
				CreateSummariesDTO(
					chat_id=chat.id,
					llm_model=LLMModelType.claude_sonnet,
					chapters=[ChapterRange(from_message_id=messages[0].id, until_message_id=messages[1].id)],
				),
				owner_id,
			)

		agent_gateway.submit.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_summarize_read_only_chat(self, service, chat_gateway, chat, owner_id):
		chat_gateway.get_one.return_value = chat.model_copy(update={"scene_id": None})

		with pytest.raises(ChatReadOnlyException):
			await service.summarize(
				CreateSummariesDTO(
					chat_id=chat.id,
					llm_model=LLMModelType.claude_sonnet,
					chapters=[ChapterRange(from_message_id=uuid4(), until_message_id=uuid4())],
				),
				owner_id,
			)

	@pytest.mark.asyncio
	async def test_handle_result_completes_and_archives(self, service, repository, events, chat):
		pending = _summary(chat.id)
		completed = pending.model_copy(update={"status": SummaryStatus.COMPLETED, "content": "EVENTS: ..."})
		repository.get_one.return_value = pending
		repository.complete.return_value = completed
		repository.archive_messages.return_value = 2

		result = await service.handle_result(
			SummaryResult(summary_id=pending.id, chat_id=chat.id, text=" EVENTS: ... ")
		)

		assert result == completed
		repository.complete.assert_awaited_once_with(pending.id, "EVENTS: ...", len("EVENTS: ..."))
		repository.archive_messages.assert_awaited_once_with(pending.id)
		repository.release_messages.assert_not_awaited()
		events.publish_summary.assert_called_once_with(chat.id, completed)
		repository.dispatch_next_queued.assert_awaited_once_with(chat.id)

	@pytest.mark.asyncio
	async def test_handle_result_error_releases_messages(self, service, repository, chat):
		pending = _summary(chat.id)
		repository.get_one.return_value = pending
		repository.fail.return_value = pending.model_copy(update={"status": SummaryStatus.FAILED})
		error = LLMErrorResponse(error_code="x", status=503, reason="down", message="provider down")

		await service.handle_result(SummaryResult(summary_id=pending.id, chat_id=chat.id, error=error))

		repository.fail.assert_awaited_once_with(pending.id, "provider down")
		repository.release_messages.assert_awaited_once_with(pending.id)
		repository.archive_messages.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_handle_result_empty_text_fails(self, service, repository, chat):
		pending = _summary(chat.id)
		repository.get_one.return_value = pending
		repository.fail.return_value = pending.model_copy(update={"status": SummaryStatus.FAILED})

		await service.handle_result(SummaryResult(summary_id=pending.id, chat_id=chat.id, text="   "))

		repository.fail.assert_awaited_once()
		repository.complete.assert_not_awaited()

	@pytest.mark.asyncio
	@pytest.mark.parametrize("status", [SummaryStatus.COMPLETED, SummaryStatus.FAILED, SummaryStatus.QUEUED])
	async def test_handle_result_ignores_non_pending(self, service, repository, chat, status):
		summary = _summary(chat.id, status=status)
		repository.get_one.return_value = summary

		result = await service.handle_result(SummaryResult(summary_id=summary.id, chat_id=chat.id, text="dup"))

		assert result is None
		repository.complete.assert_not_awaited()
		repository.fail.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_mock_model_completes_inline(self, service, repository, agent_gateway, chat, messages):
		pending = _summary(chat.id, model=LLMModelType.testing_mock)
		repository.dispatch_next_queued.side_effect = [pending, None]
		repository.list_summary_messages.return_value = messages
		repository.get_one.return_value = pending
		repository.complete.return_value = pending.model_copy(update={"status": SummaryStatus.COMPLETED})

		await service._pump(chat.id)

		agent_gateway.submit.assert_not_awaited()
		repository.complete.assert_awaited_once()
		repository.archive_messages.assert_awaited_once_with(pending.id)
		assert repository.dispatch_next_queued.await_count == 2

	@pytest.mark.asyncio
	async def test_publish_failure_fails_and_moves_on(self, service, repository, agent_gateway, chat, messages):
		first = _summary(chat.id)
		repository.dispatch_next_queued.side_effect = [first, None]
		repository.list_summary_messages.return_value = messages
		repository.fail.return_value = first.model_copy(update={"status": SummaryStatus.FAILED})
		agent_gateway.submit.side_effect = LLMGatewayException(message="broker down")

		await service._pump(chat.id)

		repository.fail.assert_awaited_once_with(first.id, "broker down")
		repository.release_messages.assert_awaited_once_with(first.id)
		assert repository.dispatch_next_queued.await_count == 2

	@pytest.mark.asyncio
	async def test_expired_pending_are_released(self, service, repository, chat, owner_id, events):
		stuck = _summary(chat.id, status=SummaryStatus.FAILED)
		repository.expire_pending.return_value = [stuck.id]
		repository.get_one.return_value = stuck
		repository.list_source_messages.return_value = []

		await service.list_chapters(chat.id, owner_id)

		repository.release_messages.assert_awaited_once_with(stuck.id)
		events.publish_summary.assert_called_once_with(chat.id, stuck)

	@pytest.mark.asyncio
	async def test_update_requires_completed(self, service, repository, chat, owner_id):
		repository.get_one.return_value = _summary(chat.id, status=SummaryStatus.PENDING)

		with pytest.raises(SummaryNotEditableException):
			await service.update(uuid4(), UpdateSummaryDTO(content="new"), owner_id)

	@pytest.mark.asyncio
	async def test_update_recounts_tokens(self, service, repository, chat, owner_id, events):
		summary = _summary(chat.id, status=SummaryStatus.COMPLETED, content="old")
		updated = summary.model_copy(update={"content": "brand new"})
		repository.get_one.return_value = summary
		repository.update_content.return_value = updated

		result = await service.update(summary.id, UpdateSummaryDTO(content="brand new"), owner_id)

		assert result == updated
		repository.update_content.assert_awaited_once_with(summary.id, "brand new", len("brand new"))
		events.publish_summary.assert_called_once_with(chat.id, updated)

	@pytest.mark.asyncio
	async def test_get_one_rejects_foreign_owner(self, service, repository, chat):
		repository.get_one.return_value = _summary(chat.id)

		with pytest.raises(HTTPException) as exc:
			await service.get_one(uuid4(), uuid4())

		assert exc.value.status_code == 403

	@pytest.mark.asyncio
	async def test_prompt_summaries_only_completed(self, service, repository, chat):
		await service.prompt_summaries(chat.id)

		repository.list_for_chat.assert_awaited_once_with(chat.id, [SummaryStatus.COMPLETED])
