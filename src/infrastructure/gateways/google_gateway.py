import json
from dataclasses import dataclass
from logging import Logger

from google import genai
from google.genai import types
from google.genai.types import UserContent, ModelContent

from domain.models import ChatRoles
from src.application.ports import UserMessageDTO
from src.application.ports import ILLMChatGateway
from src.infrastructure.exceptions import JSONParsingException, ContentSafetyException, LLMGatewayException


_OK_FINISH_REASONS = (types.FinishReason.STOP, types.FinishReason.MAX_TOKENS)


@dataclass
class GoogleGateway(ILLMChatGateway):
	logger: Logger
	_client: genai.Client
	_model_name: str
	_config: types.GenerateContentConfig

	async def generate_response(self, user_message: str, history: list[UserMessageDTO] | None = None) -> dict:
		response = None
		try:
			chat_history = []
			if history:
				for message in history:
					if message.role == ChatRoles.USER:
						chat_history.append(UserContent(parts=[types.Part(text=message.message)]))
					elif message.role == ChatRoles.MODEL:
						chat_history.append(ModelContent(parts=[types.Part(text=message.message)]))

			base_config = types.GenerateContentConfig(
				temperature=0.2, system_instruction="You are a strict data formatting assistant."
			)

			if chat_history:
				chat = self._client.aio.chats.create(model="gemini-3.5-flash", history=chat_history, config=base_config)
			else:
				chat = self._client.aio.chats.create(model="gemini-3.5-flash", config=base_config)

			response = chat.send_message(user_message)

			finish_reason = response.candidates[0].finish_reason if response.candidates else None
			if finish_reason is not None and finish_reason not in _OK_FINISH_REASONS:
				self.logger.error("[Ошибка]: Ответ заблокирован фильтрами безопасности Gemini.")
				raise ContentSafetyException(
					message="Ответ заблокирован фильтрами безопасности Gemini",
					details={"finish_reason": str(finish_reason)},
				)

			parsed_data = json.loads(response.text)
			return parsed_data

		except json.JSONDecodeError as e:
			self.logger.error("[Ошибка]: Сбой парсинга JSON.")
			raise JSONParsingException(
				message="Сбой парсинга JSON ответа от LLM",
				details={"original_error": str(e), "response_text": getattr(response, "text", "N/A")},
			)
		except ContentSafetyException:
			raise
		except Exception as e:
			self.logger.error(f"[Ошибка]: {e}")
			raise LLMGatewayException(
				message=f"Ошибка шлюза LLM: {str(e)}",
				details={"original_error": str(e), "error_type": type(e).__name__},
			)
