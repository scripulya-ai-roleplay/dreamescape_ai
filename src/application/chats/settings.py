from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ControlBehavior(str, Enum):
	CONTROL = "Control"
	DONT_CONTROL = "Don't Control"


class Perspective(str, Enum):
	FIRST_PERSON = "1st Person"
	SECOND_PERSON = "2nd Person"
	THIRD_PERSON = "3rd Person"


class Preset(str, Enum):
	LOW = "Low"
	MID = "Mid"
	HIGH = "High"
	MAX = "Max"


class ResponseLength(str, Enum):
	SHORT = "Short"
	MEDIUM = "Medium"
	LONG = "Long"


class TokenLimit(str, Enum):
	CAPPED = "Capped"
	HIGH = "High"
	MAX = "Max"


class Toggle(str, Enum):
	ON = "On"
	OFF = "Off"


class ReasoningEffort(str, Enum):
	MIN = "Min"
	LOW = "Low"
	MID = "Mid"
	HIGH = "High"


class TemperatureSettings(BaseModel):
	preset: Preset
	value: float = Field(..., ge=0.0, description="Controls AI creativity")


class FunctionsSettings(BaseModel):
	characterNameGenerator: bool = Field(default=True, description="Generates unique character names using AI")


class ChatSettings(BaseModel):
	"""Per-chat LLM generation settings.

	The canonical wire contract shared by the DB (JSONB), the settings HTTP
	endpoint, and the LLMRequest payload sent to scripulya_agent. Field names and
	enum values are kept verbatim because they cross the RabbitMQ/HTTP boundary
	as JSON and must serialize identically on both sides.
	"""

	aiControlBehavior: ControlBehavior
	continueBehavior: ControlBehavior
	perspective: Perspective
	temperature: TemperatureSettings
	responseLength: ResponseLength
	responseTokenLimit: TokenLimit = Field(description="Max token limit. 2k tokens noted in UI.")
	reasoning: Toggle
	reasoningEffort: ReasoningEffort
	aiMediaPicker: Toggle
	contextLimitOverride: Optional[int] = Field(
		default=None,
		ge=1,
		le=1048576,
		description="Set context limit to save cost. Max 1,048,576.",
	)
	functions: FunctionsSettings
