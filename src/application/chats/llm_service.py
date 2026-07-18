import logging
from dataclasses import dataclass

from src.application.message.schemas import MessagesFilterDto
from src.application.ports import (
	ICharacterGateway,
	IChatsService,
	IChatEventGateway,
	IChatGateway,
	IChatSettingsGateway,
	IGatewayFactory,
	IMessageService,
	IPromptService,
	ISceneGateway,
	UserMessageDTO,
)
from src.domain.models import ChatRoles, Message, MessageStatus
from src.infrastructure.exceptions import PersonaRequiredException


@dataclass
class LLMChatsService(IChatsService):
	"""Orchestrates a single chat turn: builds the system prompt (scene, characters,
	and the user's "play-as" persona), persists the user's message, and submits the
	LLM request. All message persistence is delegated to MessageService — this
	service performs no DB writes of its own."""

	gateway_factory: IGatewayFactory
	message_service: IMessageService
	chat_settings_gateway: IChatSettingsGateway
	chat_gateway: IChatGateway
	scene_gateway: ISceneGateway
	character_gateway: ICharacterGateway
	prompt_service: IPromptService
	_events: IChatEventGateway
	logger: logging.Logger

	async def send_message(self, chat_dto: UserMessageDTO) -> Message:
		self.logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		history_page = await self.message_service.search(MessagesFilterDto(chats_ids=[chat_dto.chat_id]))
		history = [
			UserMessageDTO(message=m.message, chat_id=chat_dto.chat_id, llm_model=chat_dto.llm_model, role=m.role)
			for m in reversed(history_page.items)
		]

		chat = await self.chat_gateway.get_one(chat_dto.chat_id)
		scene = await self.scene_gateway.get_one(chat.scene_id)
		characters = await self.character_gateway.get_for_scene(chat.scene_id)
		# A story can't be played without a persona: reject early (before persisting
		# the user message) so the global handler returns a graceful 400 instead of a None.
		if chat.user_character_id is None:
			raise PersonaRequiredException()
		user_character = await self.character_gateway.get_one(chat.user_character_id)
		system_prompt = self.prompt_service.build_system_prompt(scene, characters, user_character)

		user_message = await self.message_service.send_message(
			Message(
				message=chat_dto.message,
				chat_id=chat_dto.chat_id,
				role=chat_dto.role,
				status=MessageStatus.COMPLETED,
			)
		)

		chat_settings = await self.chat_settings_gateway.get_for_chat(chat_dto.chat_id)

		history_preview = "\n\n".join(f"[{m.role}] {m.message}" for m in history) or "(none)"
		self.logger.info(
			f"LLM prompt for chat {chat_dto.chat_id} | model={chat_dto.llm_model}\n"
			f"===== SYSTEM PROMPT =====\n{system_prompt}\n"
			f"===== HISTORY ({len(history)} turns) =====\n{history_preview}\n"
			f"===== NEW MESSAGE [{chat_dto.role}] =====\n{chat_dto.message}\n"
			f"===== END PROMPT ====="
		)

		response = await gateway.submit(chat_dto, history, chat_settings=chat_settings, system_prompt=system_prompt)
		if response is not None:
			model_message = await self.message_service.send_message(
				Message(
					message=response.text,
					chat_id=chat_dto.chat_id,
					role=ChatRoles.MODEL,
					status=MessageStatus.COMPLETED,
				)
			)
			self._events.publish_message(chat_dto.chat_id, model_message)

		return user_message
