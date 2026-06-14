from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field

class Settings(BaseSettings):
	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		case_sensitive=False,
		extra="ignore",
	)

	APP_NAME: str = "Gemini Chat"
	APP_VERSION: str = "0.0.1"
	DEBUG: bool = False
	HOST: str = "0.0.0.0"
	PORT: int = 8000

	GEMINI_API_KEY: str
	ANTHROPIC_API_KEY: str = ""
	QWEN_API_KEY: str = ""
	QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
	LLM_TEMPERATURE: float = 0.7
	# Database Settings
	POSTGRES_USER: str
	POSTGRES_PASSWORD: str
	POSTGRES_DB: str

	@computed_field
	@property
	def DATABASE_URL(self) -> str:
		return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@postgres:5432/{self.POSTGRES_DB}"

	# JWT Settings
	JWT_SECRET_KEY: str
	JWT_PUBLIC_KEY: str = ""
	JWT_ALGORITHM: str = "HS256"
	JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

	SYSTEM_PROMPT: str = """
    Ты — рассказчик и описываешь происходящее на основе персонажей и окружающей среды
    Тут приведены описания персонажей

    Персонажи общаются с пользователем или взаимодействуют с ним тем или иным способом
    Твоя задача — отвечать на сообщения и параллельно описывать сцену для генерации картинки. Расписывай всё примерно в 3-4 абзацах
    Твой ответ ВСЕГДА должен быть строго в формате JSON:
    {
        "text": "Твой текстовый ответ",
    }
    """


settings = Settings()  # type: ignore
