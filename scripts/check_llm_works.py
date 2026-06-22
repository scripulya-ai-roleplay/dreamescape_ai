from google import genai
from google.genai import types
from google.genai.types import Part, UserContent, ModelContent

client = genai.Client()

# 1. Structure existing history
saved_history = [
	UserContent(parts=[Part(text="Hello.")]),
	ModelContent(parts=[Part(text="Hi, how can I help?")]),
]

# 2. Resume chat with base settings
base_config = types.GenerateContentConfig(
	temperature=0.2, system_instruction="You are a strict data formatting assistant."
)

chat = client.chats.create(model="gemini-3.5-flash", history=saved_history, config=base_config)

# 3. Override settings mid-chat for a specific turn
mid_chat_config = types.GenerateContentConfig(
	temperature=0.9,  # Increasing creativity temporarily
	max_output_tokens=500,
)

response = chat.send_message("Write a short, creative poem about a database.", config=mid_chat_config)

print(response.text)
