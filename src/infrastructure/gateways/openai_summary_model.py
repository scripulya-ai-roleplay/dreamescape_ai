import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from src.application.ports.summary_model import ISummaryModel
from src.conf import settings
from src.domain.models import ChatRoles, Message
from src.infrastructure.logging.logger import Logger

_SYSTEM_PROMPT = (
	"You maintain a rolling third-person summary of an ongoing roleplay conversation. "
	"Incorporate the new messages into the existing summary, preserving the narrative order, "
	"established facts, relationships, and any unresolved threads. Drop nothing still relevant. "
	"Output ONLY the updated summary prose. Keep it under 500 tokens. No preamble, no headings."
)


@dataclass
class OpenAISummaryModel(ISummaryModel):
	_client: AsyncOpenAI
	_model: str = settings.SUMMARY_MODEL
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def summarize(self, prior_summary: str | None, messages: list[Message]) -> str:
		prior = (prior_summary or "").strip()
		prior_block = f"Existing summary:\n{prior}" if prior else "There is no existing summary yet; start one."
		transcript = "\n".join(self._format(message) for message in messages) or "(no messages)"
		user_content = f"{prior_block}\n\nNew messages to fold in:\n{transcript}"

		response = await self._client.chat.completions.create(
			model=self._model,
			temperature=0.3,
			max_tokens=settings.SUMMARY_TOKEN_CAP,
			messages=[
				{"role": "system", "content": _SYSTEM_PROMPT},
				{"role": "user", "content": user_content},
			],
		)
		return (response.choices[0].message.content or "").strip()

	@staticmethod
	def _format(message: Message) -> str:
		label = "User" if message.role == ChatRoles.USER else "Character"
		return f"[{label}] {message.message}"
