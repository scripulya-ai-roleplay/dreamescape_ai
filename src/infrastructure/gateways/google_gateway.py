import json
from dataclasses import dataclass
from logging import Logger

from google import genai
from google.genai import types

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
			chat_history = None
			if history:
				chat_history = [types.Content(role=m.role.value, parts=[types.Part(text=m.message)]) for m in history]

			chat = self._client.aio.chats.create(
				model=self._model_name,
				config=self._config,
				history=chat_history,
			)

			response = await chat.send_message(user_message)

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
