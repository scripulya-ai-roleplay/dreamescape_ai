import json
from dataclasses import dataclass
from logging import Logger

import google.generativeai as genai
from google.generativeai import ChatSession

from src.application.ports import ILLMChatGateway
from src.infrastructure.exceptions import (
    JSONParsingException,
    ContentSafetyException,
    LLMGatewayException
)


@dataclass
class GoogleGateway(ILLMChatGateway):
    chat: ChatSession
    logger: Logger

    async def generate_response(self, user_message: str) -> dict:
        try:
            response = self.chat.send_message(user_message)

            parsed_data = json.loads(response.text)
            return parsed_data

        except json.JSONDecodeError as e:
            self.logger.error("[Ошибка]: Сбой парсинга JSON.")
            raise JSONParsingException(
                message="Сбой парсинга JSON ответа от LLM",
                details={"original_error": str(e), "response_text": getattr(response, 'text', 'N/A')}
            )
        except genai.types.generation_types.StopCandidateException as e:
            self.logger.error("[Ошибка]: Ответ заблокирован фильтрами безопасности Gemini.")
            raise ContentSafetyException(
                message="Ответ заблокирован фильтрами безопасности Gemini",
                details={"original_error": str(e)}
            )
        except Exception as e:
            self.logger.error(f"[Ошибка]: {e}")
            raise LLMGatewayException(
                message=f"Ошибка шлюза LLM: {str(e)}",
                details={"original_error": str(e), "error_type": type(e).__name__}
            )

