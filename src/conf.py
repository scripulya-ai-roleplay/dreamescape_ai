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

	# --- Redis heartbeat (anti-hang) ---
	# Tuned so a legitimately-slow generation never false-positives: as long as the
	# agent keeps refreshing :alive, the watchdog leaves it alone.
	REDIS_URL: str = "redis://redis:6379/0"
	LLM_HEARTBEAT_ALIVE_TTL: int = 30  # no refresh for this long => agent considered dead
	LLM_HEARTBEAT_GRACE_TTL: int = 45  # initial TTL on submit; must be > ALIVE_TTL
	LLM_HEARTBEAT_HARD_DEADLINE_SECONDS: int = 1800  # backstop so inflight keys can't leak
	LLM_SWEEP_INTERVAL_SECONDS: int = 10

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
    You are the narrator of an interactive roleplay. You describe what happens based on the
    Characters, the Scene, and the Player Character provided above.

    WHO IS WHO
    - The human player and their Player Character are one and the same person. When the human
      sends a message, that IS the Player Character speaking and acting. There is no separate
      "user" entity — do not invent one and do not treat the Player Character as just another
      character.
    - You (the narrator) portray only the world and the non-player Characters. You NEVER portray
      the Player Character.

    HOW TO RESPOND
    - Describe how the world and the other Characters interact with the Player Character in the
      SECOND PERSON, addressing them as "you" (for example: "someone looked at you").
    - Never write the Player Character's dialogue, actions, or thoughts. React to what they do;
      never decide for them.
    - Write roughly 3-4 paragraphs, vivid enough to generate an accompanying image.

    OUTPUT FORMAT
    Your response must ALWAYS be strictly JSON:
    {
        "text": "Your narration as described above"
    }
    """


settings = Settings()  # type: ignore
