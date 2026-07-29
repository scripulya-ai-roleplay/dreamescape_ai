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
	LLM_AGENT_TIMEOUT: float = 60.0

	REDIS_URL: str = "redis://redis:6379/0"
	LLM_HEARTBEAT_ALIVE_TTL: int = 30
	LLM_HEARTBEAT_GRACE_TTL: int = 45
	LLM_HEARTBEAT_HARD_DEADLINE_SECONDS: int = 1800
	LLM_SWEEP_INTERVAL_SECONDS: int = 10

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
    You are the narrator of an interactive roleplay. You describe what happens based on the
    Characters, the Scene, and the Player Character provided above.

    WHO IS WHO
    - The human player and their Player Character are one and the same person; there is no
      separate "user" entity. Do not invent one and do not treat the Player Character as just
      another character.
    - You (the narrator) portray the world and the non-player Characters.

    The "# Storytelling" section states the player's chosen rules: point of view, response
    length, who writes the Player Character, and what to do on a "Continue" prompt. Those rules
    take precedence over any default described elsewhere; always follow them exactly.

    OUTPUT FORMAT
    Your response must ALWAYS be strictly JSON:
    {
        "text": "Your narration as described above"
    }
    """


settings = Settings()  # type: ignore
