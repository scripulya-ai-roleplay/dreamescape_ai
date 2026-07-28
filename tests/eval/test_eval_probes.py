import json
import os
import uuid
from pathlib import Path

import pytest
import requests

# Eval probes replay scripted transcripts against a LIVE stack and assert memory behavior
# (long-range callback, reversal, multi-hop). They need the full environment up (postgres+pgvector,
# redis, rabbitmq, backend, agent) and a real OPENAI_API_KEY for embeddings/summary, so they are
# skipped by default. Run via `python scripts/run_eval.py` or `pytest -m eval` with EVAL_ENABLED=1.

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"
BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")
SEED_USER_ID = "5dbdc924-968a-4c50-94a8-44cdd165e460"


def _transcripts():
	if not TRANSCRIPTS_DIR.exists():
		return []
	return sorted(TRANSCRIPTS_DIR.glob("*.json"))


def _token():
	from src.application.auth.jwt_service import JWTService
	from src.conf import settings
	from src.domain.models import User, UserRole

	jwt = JWTService(
		logger=__import__("logging").getLogger("eval"),
		private_key=settings.JWT_SECRET_KEY,
		public_key=settings.JWT_PUBLIC_KEY,
		algorithm=settings.JWT_ALGORITHM,
		access_token_expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
	)
	return jwt.create_token(User(id=uuid.UUID(SEED_USER_ID), username="eval", role=UserRole.API))


@pytest.mark.eval
@pytest.mark.parametrize("transcript_path", _transcripts(), ids=lambda p: p.stem)
def test_probe(transcript_path):
	if os.getenv("EVAL_ENABLED") != "1":
		pytest.skip("EVAL_ENABLED!=1; eval probes need a live stack + OPENAI_API_KEY")

	transcript = json.loads(transcript_path.read_text())
	headers = {"Authorization": f"Bearer {_token()}"}
	session = requests.Session()

	chat = session.post(f"{BACKEND_HOST}/api/v1/chats", headers=headers, json={}).json()
	chat_id = chat["result"]["id"]

	for turn in transcript["setup"]:
		session.post(
			f"{BACKEND_HOST}/api/v1/messages",
			headers=headers,
			json={"chat_id": chat_id, "message": turn["text"], "llm_model": "testing_mock"},
		)
	for _ in range(transcript.get("filler_turns", 0)):
		session.post(
			f"{BACKEND_HOST}/api/v1/messages",
			headers=headers,
			json={"chat_id": chat_id, "message": "filler turn", "llm_model": "testing_mock"},
		)

	session.post(
		f"{BACKEND_HOST}/api/v1/messages",
		headers=headers,
		json={"chat_id": chat_id, "message": transcript["probe"]["user"], "llm_model": "testing_mock"},
	)

	usage = session.get(f"{BACKEND_HOST}/api/v1/chats/{chat_id}/context-usage", headers=headers).json()["result"]
	expected = transcript["probe"]["expect_in_context"]
	assert expected in usage["system_prompt"], f"probe failed: '{expected}' not in assembled context"
