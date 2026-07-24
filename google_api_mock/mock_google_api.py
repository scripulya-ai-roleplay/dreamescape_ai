"""
Mock Google API service for testing purposes.
This service mimics the Google Generative AI API responses.
"""

import logging
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
logging.basicConfig(level=logging.INFO)


class GenerateRequest(BaseModel):
	contents: list[dict[str, Any]]


@app.post("/v1beta/models/gemini-1.5-flash-latest:generateContent")
async def generate_content(request: GenerateRequest):
	"""Mock endpoint for content generation"""
	try:
		logging.info(f"Received request: {request}")

		# Extract user prompt
		user_text = ""
		if request.contents:
			parts = request.contents[0].get("parts", [])
			if parts:
				user_text = parts[0].get("text", "")

		# Mock response
		response = {
			"candidates": [
				{
					"content": {"parts": [{"text": f"This is a mock response to: {user_text}"}], "role": "model"},
					"finishReason": "STOP",
					"index": 0,
					"safetyRatings": [
						{"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "NEGLIGIBLE"},
						{"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"},
						{"category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE"},
						{"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "NEGLIGIBLE"},
					],
				}
			]
		}

		return response

	except Exception as e:
		logging.error(f"Error processing request: {e}")
		return {"error": "Internal server error"}


@app.get("/health")
async def health_check():
	"""Health check endpoint"""
	return {"status": "healthy"}
