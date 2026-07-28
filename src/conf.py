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

	# --- Hybrid memory ---
	SUMMARY_ENABLED: bool = True
	VECTOR_MEMORY_ENABLED: bool = True
	GRAPH_MEMORY_ENABLED: bool = False  # needs FalkorDB (see scripulya_deploy); degrades to empty when off
	MEMORY_SOURCE_TIMEOUT_MS: int = 800
	MEMORY_INGEST_IDEMPOTENCY_TTL_SECONDS: int = 7 * 24 * 3600
	DEFAULT_CONTEXT_LIMIT: int = 32_000
	HISTORY_MAX_TAIL: int = 200

	# Summary (rolling)
	SUMMARY_TRIGGER_TOKENS: int = 2000
	SUMMARY_FOLD_BATCH_TOKENS: int = 1000
	SUMMARY_TOKEN_CAP: int = 500
	SUMMARY_MODEL: str = "gpt-4o-mini"

	# Vector (pgvector verbatim recall)
	EMBEDDING_MODEL: str = "text-embedding-3-small"
	EMBEDDING_DIMENSION: int = 1536
	MEMORIES_TOKEN_CAP: int = 600
	MEMORIES_MAX_DISTANCE: float = 0.5
	MEMORIES_K: int = 5
	MEMORIES_EF_SEARCH: int = 40
	MEMORY_SUMMARY_DEDUP_SIMILARITY: float = 0.92

	# Reminder
	REMINDER_TOKEN_CAP: int = 150

	# Graph (Graphiti + FalkorDB) — current-state facts, invalidation-aware
	FALKORDB_HOST: str = "falkordb"
	FALKORDB_PORT: int = 6379
	FALKORDB_USERNAME: str = ""
	FALKORDB_PASSWORD: str = ""
	FALKORDB_DATABASE: str = "default_db"
	GRAPH_EXTRACTION_MODEL: str = "gpt-4o-mini"  # cheap model for entity/relation extraction
	GRAPH_SMALL_MODEL: str = "gpt-4o-mini"
	GRAPH_MEMORY_SEARCH_RESULTS: int = 10
	GRAPH_MEMORY_MAX_FACTS: int = 12

	# Vendor client (embedder + summary model). Behind ports so Google/other vendors can swap in.
	OPENAI_API_KEY: str = ""
	OPENAI_BASE_URL: str = "https://api.openai.com/v1"

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
