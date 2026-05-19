import google.generativeai as genai
from google.generativeai import GenerativeModel, ChatSession
from pydantic_settings import BaseSettings, SettingsConfigDict
from google.generativeai.types import HarmCategory, HarmBlockThreshold


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
    {
        "Aza": "20-метровая демоница, которую зовут Аза. Аза по своей внешности очень красивая женщина но с рогами и хвостом как у демоницы, которая хочет съесть пользователя. Ей в целом безразличен пользователь, и она не хочет с ним церемониться. Пользователь всего лишь очередная закуска, а она слишком голодная, чтобы с пользователем церемониться"
    }
    
    Сцена - пользователь просыпается посреди тарелки с фруктами и ты переключаешь своё внимание
    на пользователя после того как съела один из фруктов, почти демонстративно
     
    Персонажи общаются с пользователем или взаимодействуют с ним тем или иным способом
    Твоя задача — отвечать на сообщения и параллельно описывать сцену для генерации картинки. Расписывай всё примерно в 3-4 абзацах
    Твой ответ ВСЕГДА должен быть строго в формате JSON:
    {
        "text": "Твой текстовый ответ",
    }
    """
    MODEL: GenerativeModel = genai.GenerativeModel(
        model_name="gemini-3-flash-preview",
        system_instruction=SYSTEM_PROMPT,
        # Форсируем JSON-вывод на уровне API
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.7,
        },
        # Отключаем фильтры безопасности насколько это возможно
        safety_settings={
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        },
    )

    CHAT: ChatSession = MODEL.start_chat(history=[])


settings = Settings() # type: ignore
