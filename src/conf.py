from pydantic_settings import BaseSettings, SettingsConfigDict


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

	GEMINI_API_KEY: str = ""
	ANTHROPIC_API_KEY: str = ""
	QWEN_API_KEY: str = ""
	QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
	LLM_TEMPERATURE: float = 0.7

	# --- RabbitMQ / scripulya_agent integration ---
	# The backend delegates LLM generation to the scripulya_agent worker over these queues.
	# When false, a MockScripulyaAgentClient is used and the RabbitMQ broker is not started,
	# so the app runs without RabbitMQ/scripulya_agent (local docker). Real models then drop
	# their requests; use the testing_mock model for a fully offline chat.
	LLM_AGENT_ENABLED: bool = True
	RABBIT_URL: str = "amqp://guest:guest@rabbitmq:5672/"
	LLM_AGENT_REQUEST_QUEUE: str = "llm.agent.request"
	LLM_AGENT_RESULT_QUEUE: str = "llm.agent.result"
	LLM_AGENT_TIMEOUT: float = 60.0  # seconds to await an LLMResult before failing the request

	# Database Settings
	DATABASE_URL: str = "postgresql+asyncpg://user:password@postgres:5432/dbname"

	# JWT Settings
	JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
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
