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

	LLM_AGENT_ENABLED: bool = True
	RABBIT_URL: str = "amqp://guest:guest@rabbitmq:5672/"
	LLM_AGENT_REQUEST_QUEUE: str = "llm.agent.request"
	LLM_AGENT_RESULT_QUEUE: str = "llm.agent.result"
	LLM_AGENT_TIMEOUT: float = 60.0  # seconds to await an LLMResult before failing the request

	# Database Settings
	DATABASE_URL: str = "postgresql+asyncpg://user:password@postgres:5432/dbname"

	MINIO_INTERNAL_ENDPOINT: str = "minio:9000"
	MINIO_PUBLIC_ENDPOINT: str = "localhost:9000"
	MINIO_ROOT_USER: str = "minioadmin"
	MINIO_ROOT_PASSWORD: str = "minioadmin"
	MINIO_SECURE: bool = False
	MINIO_BUCKET_PUBLIC: str = "scripulya-public"
	MINIO_BUCKET_PRIVATE: str = "scripulya-private"
	MINIO_PRESIGN_EXPIRY_SECONDS: int = 900
	MEDIA_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024

	JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
	JWT_PUBLIC_KEY: str = ""
	JWT_ALGORITHM: str = "HS256"
	JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

	SYSTEM_PROMPT: str = """
    You are a narrator and describe what is happening based on the characters and the environment
    The character descriptions are provided here

    Characters communicate with the user or interact with them in one way or another
    Your task is to respond to messages and, at the same time, describe the scene for image generation. Write it in roughly 3-4 paragraphs
    Your response must ALWAYS be strictly in JSON format:
    The user plays as the character indicated here under the User section. Describe how the world and the other characters
    interact with the user in the second person, for example: 'someone looked at you' etc.
    {
        "text": "Your text response",
    }
    """


settings = Settings()  # type: ignore
