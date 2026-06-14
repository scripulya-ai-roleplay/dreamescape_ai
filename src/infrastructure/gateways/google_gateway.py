import json
from dataclasses import dataclass
from logging import Logger

import google.generativeai as genai
from google.generativeai import GenerativeModel

from src.application.ports import UserMessageDTO
from src.application.ports import ILLMChatGateway
from src.infrastructure.exceptions import JSONParsingException, ContentSafetyException, LLMGatewayException


@dataclass
class GoogleGateway(ILLMChatGateway):
	logger: Logger
	_client: GenerativeModel

	async def generate_response(self, user_message: str, history: list[UserMessageDTO] | None = None) -> dict:
		try:
			if history:
				chat_history = [{"role": m.role.value, "parts": [m.message]} for m in history]
				chat = self._client.start_chat(history=chat_history)
			else:
				chat = self._client.start_chat()

			response = chat.send_message(user_message)

			parsed_data = json.loads(response.text)
			return parsed_data

		except json.JSONDecodeError as e:
			self.logger.error("[Ошибка]: Сбой парсинга JSON.")
			raise JSONParsingException(
				message="Сбой парсинга JSON ответа от LLM",
				details={"original_error": str(e), "response_text": getattr(response, "text", "N/A")},
			)
		except genai.types.generation_types.StopCandidateException as e:
			self.logger.error("[Ошибка]: Ответ заблокирован фильтрами безопасности Gemini.")
			raise ContentSafetyException(
				message="Ответ заблокирован фильтрами безопасности Gemini", details={"original_error": str(e)}
			)
		except Exception as e:
			self.logger.error(f"[Ошибка]: {e}")
			raise LLMGatewayException(
				message=f"Ошибка шлюза LLM: {str(e)}",
				details={"original_error": str(e), "error_type": type(e).__name__},
			)
