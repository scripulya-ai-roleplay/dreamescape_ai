import pytest

# Chat owned by the admin user (auth_headers) with seeded messages + persona + initial message,
# so the memory endpoints have real history to summarize/budget.
PROJECT_HELP_CHAT = "048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb"
# Seeded chat with a persona + initial message but no seeded message rows.
EMPTY_E2E_CHAT = "82dc4309-0ab2-4a9d-86c9-a49f8931494a"


@pytest.mark.e2e
class TestMemoryAPI:
	"""End-to-end tests for the hybrid-memory surface (summary controls + context usage).

	These run against the live stack (postgres+pgvector, redis, backend). They avoid the
	OpenAI dependency: manual summary and context-usage assemble from DB state, and the
	embedding/summary layers degrade to empty when OPENAI_API_KEY is absent.
	"""

	def test_context_usage_returns_section_breakdown(self, client, auth_headers):
		response = client.get(f"/api/v1/chats/{PROJECT_HELP_CHAT}/context-usage", headers=auth_headers)

		assert response.status_code == 200
		result = response.json()["result"]
		assert "sections" in result
		assert "total" in result
		assert "limit" in result
		assert "system_prompt" in result
		assert result["sections"]["system"] > 0
		assert result["total"] >= result["sections"]["system"]

	def test_manual_summary_roundtrip_and_visible_in_context(self, client, auth_headers):
		content = "Manual summary: the user asked for project help and the assistant agreed."
		put = client.put(f"/api/v1/chats/{PROJECT_HELP_CHAT}/summary", json={"content": content}, headers=auth_headers)
		assert put.status_code == 200
		created = put.json()["result"]
		assert created["content"] == content
		assert created["model"] == "manual"

		got = client.get(f"/api/v1/chats/{PROJECT_HELP_CHAT}/summary", headers=auth_headers)
		assert got.status_code == 200
		assert got.json()["result"]["content"] == content

		usage = client.get(f"/api/v1/chats/{PROJECT_HELP_CHAT}/context-usage", headers=auth_headers)
		system_prompt = usage.json()["result"]["system_prompt"]
		assert "[STORY SO FAR]" in system_prompt
		assert content in system_prompt

	def test_context_usage_rejects_foreign_chat(self, client, other_auth_headers):
		response = client.get(f"/api/v1/chats/{PROJECT_HELP_CHAT}/context-usage", headers=other_auth_headers)
		assert response.status_code == 403

	def test_send_message_returns_202_with_memory_enabled(self, client, auth_headers):
		"""The enriched+budgeted send path still accepts a message (202) even when the
		embedding/summary vendor calls degrade to empty (no key in the e2e env)."""
		payload = {
			"message": "Memory e2e probe message",
			"chat_id": EMPTY_E2E_CHAT,
			"llm_model": "testing_mock",
		}
		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)
		assert response.status_code == 202
