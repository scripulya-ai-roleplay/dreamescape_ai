import time

import pytest

ADMIN_ID = "5dbdc924-968a-4c50-94a8-44cdd165e460"
SCENE_ID = "5c194d75-401f-4fa2-808c-7092153135b7"
PERSONA_ID = "43341001-4ea1-4f03-b315-811d3264b6a3"
CHAT_TITLE = "Summarization E2E Chat"


@pytest.fixture
def summarizable_chat(client, auth_headers):
	created = client.post(
		"/api/v1/chats/",
		json={"title": CHAT_TITLE, "user_id": ADMIN_ID, "scene_id": SCENE_ID, "user_character_id": PERSONA_ID},
		headers=auth_headers,
	)
	assert created.status_code == 200
	chat_id = created.json()["result"]["id"]
	initial = client.get(f"/api/v1/scenes/{SCENE_ID}/initial-messages", headers=auth_headers).json()["result"][0]
	chosen = client.post(
		f"/api/v1/chats/{chat_id}/initial-message", json={"initial_message_id": initial["id"]}, headers=auth_headers
	)
	assert chosen.status_code == 200
	for text in ("I open the lighthouse gate.", "I hide the map in my coat."):
		sent = client.post(
			"/api/v1/messages/",
			json={"chat_id": chat_id, "message": text, "llm_model": "testing_mock"},
			headers=auth_headers,
		)
		assert sent.status_code == 202
	yield chat_id
	client.delete(f"/api/v1/chats/{chat_id}", headers=auth_headers)


def _wait_for(client, auth_headers, summary_id):
	for _ in range(20):
		summary = client.get(f"/api/v1/summarization/{summary_id}", headers=auth_headers).json()["result"]
		if summary["status"] in ("completed", "failed"):
			return summary
		time.sleep(0.5)
	return summary


@pytest.mark.e2e
class TestSummarizationAPI:
	def test_chapter_summarize_archive_flow(self, client, auth_headers, summarizable_chat):
		chat_id = summarizable_chat

		chapters = client.get("/api/v1/summarization/chapters", params={"chat_id": chat_id}, headers=auth_headers)
		assert chapters.status_code == 200
		listed = chapters.json()["result"]
		assert len(listed) == 1
		chapter = listed[0]
		assert chapter["chapter_number"] == 1
		assert chapter["messages_count"] == 5
		assert chapter["tokens_count"] > 0

		payload = {
			"chat_id": chat_id,
			"llm_model": "testing_mock",
			"chapters": [
				{"from_message_id": chapter["from_message_id"], "until_message_id": chapter["until_message_id"]}
			],
		}
		created = client.post("/api/v1/summarization/", json=payload, headers=auth_headers)
		assert created.status_code == 202
		summary = _wait_for(client, auth_headers, created.json()["result"][0]["id"])
		assert summary["status"] == "completed"
		assert summary["messages_count"] == 5
		assert summary["content"]

		archived = client.get(
			"/api/v1/messages/", params={"chats_ids": chat_id, "is_archived": "true"}, headers=auth_headers
		).json()["result"]
		assert archived["count"] == 5
		assert all(m["is_archived"] and m["summary_id"] == summary["id"] for m in archived["items"])

		again = client.post("/api/v1/summarization/", json=payload, headers=auth_headers)
		assert again.status_code == 409
		assert again.json()["error"]["code"] == "SUMMARY_CHAPTER_STALE"

		after = client.get("/api/v1/summarization/chapters", params={"chat_id": chat_id}, headers=auth_headers)
		assert after.json()["result"] == []

		usage = client.get(f"/api/v1/chats/{chat_id}/context-usage", headers=auth_headers).json()["result"]
		assert usage["summaries_count"] == 1
		assert usage["history_messages_count"] == 0

		edited = client.put(
			f"/api/v1/summarization/{summary['id']}", json={"content": "Edited recap."}, headers=auth_headers
		)
		assert edited.status_code == 200
		assert edited.json()["result"]["content"] == "Edited recap."

		listing = client.get("/api/v1/summarization/", params={"chat_id": chat_id}, headers=auth_headers)
		assert listing.json()["result"]["count"] == 1

		reply = client.post(
			"/api/v1/messages/",
			json={"chat_id": chat_id, "message": "What next?", "llm_model": "testing_mock"},
			headers=auth_headers,
		)
		assert reply.status_code == 202

	def test_other_user_cannot_read_chapters(self, client, other_auth_headers, summarizable_chat):
		response = client.get(
			"/api/v1/summarization/chapters", params={"chat_id": summarizable_chat}, headers=other_auth_headers
		)
		assert response.status_code == 403

	def test_unknown_range_is_rejected(self, client, auth_headers, summarizable_chat):
		response = client.post(
			"/api/v1/summarization/",
			json={
				"chat_id": summarizable_chat,
				"llm_model": "testing_mock",
				"chapters": [
					{
						"from_message_id": "00000000-0000-0000-0000-000000000001",
						"until_message_id": "00000000-0000-0000-0000-000000000002",
					}
				],
			},
			headers=auth_headers,
		)
		assert response.status_code == 409
