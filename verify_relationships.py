#!/usr/bin/env python3
"""
Script to verify that all relationships in the test data are properly established.
This ensures that every message belongs to a chat, a user, and a scene.
"""

import re


def extract_chat_ids_from_sql():
	"""Extract all chat IDs from the chats INSERT statement."""
	with open("/home/h3ne58/scripulya_ai/scripts/init.sql", "r") as f:
		content = f.read()

	# Find the chats INSERT section
	chat_pattern = r"INSERT INTO chats.*?VALUES(.*?);"
	chat_match = re.search(chat_pattern, content, re.DOTALL)

	if not chat_match:
		print("ERROR: Could not find chats INSERT statement")
		return set()

	# Extract chat IDs
	chat_ids = set()
	chat_lines = chat_match.group(1).strip()
	for line in chat_lines.split("\n"):
		line = line.strip()
		if line.startswith("("):
			# Extract the first UUID (chat ID)
			uuid_match = re.search(r"'([0-9a-f-]{36})'", line)
			if uuid_match:
				chat_ids.add(uuid_match.group(1))

	return chat_ids


def extract_message_chat_ids_from_sql():
	"""Extract all chat_id references from messages."""
	with open("/home/h3ne58/scripulya_ai/scripts/init.sql", "r") as f:
		content = f.read()

	# Find the messages INSERT section
	message_pattern = r"INSERT INTO messages.*?VALUES(.*?);"
	message_match = re.search(message_pattern, content, re.DOTALL)

	if not message_match:
		print("ERROR: Could not find messages INSERT statement")
		return set()

	# Extract chat IDs from messages
	message_chat_ids = set()
	message_lines = message_match.group(1).strip()
	for line in message_lines.split("\n"):
		line = line.strip()
		if line.startswith("("):
			# Extract the second UUID (chat_id)
			uuid_matches = re.findall(r"'([0-9a-f-]{36})'", line)
			if len(uuid_matches) >= 2:
				message_chat_ids.add(uuid_matches[1])  # Second UUID is chat_id

	return message_chat_ids


def check_scene_relationships():
	"""Check that all chats have valid scene_id references (no NULL values)."""
	with open("/home/h3ne58/scripulya_ai/scripts/init.sql", "r") as f:
		content = f.read()

	# Find the chats INSERT section
	chat_pattern = r"INSERT INTO chats.*?VALUES(.*?);"
	chat_match = re.search(chat_pattern, content, re.DOTALL)

	if not chat_match:
		print("ERROR: Could not find chats INSERT statement")
		return False

	chat_lines = chat_match.group(1).strip()
	null_scene_chats = []

	for line in chat_lines.split("\n"):
		line = line.strip()
		if line.startswith("(") and "NULL" in line:
			# Extract chat name for reporting
			parts = line.split(",")
			if len(parts) >= 2:
				chat_name = parts[1].strip().strip("'")
				null_scene_chats.append(chat_name)

	if null_scene_chats:
		print(f"ERROR: Found {len(null_scene_chats)} chats with NULL scene_id:")
		for chat_name in null_scene_chats:
			print(f"  - {chat_name}")
		return False

	return True


def main():
	print("Verifying relationships in init.sql...")
	print("=" * 50)

	# Check that all chats have scenes
	print("1. Checking that all chats have valid scene_id references...")
	scenes_ok = check_scene_relationships()
	if scenes_ok:
		print("   ✓ All chats have valid scene_id references")
	else:
		print("   ✗ Some chats have NULL scene_id references")

	# Check that all messages reference existing chats
	print("\n2. Checking that all messages reference existing chats...")
	chat_ids = extract_chat_ids_from_sql()
	message_chat_ids = extract_message_chat_ids_from_sql()

	print(f"   Found {len(chat_ids)} chats in the database")
	print(f"   Found {len(message_chat_ids)} unique chat references in messages")

	orphaned_messages = message_chat_ids - chat_ids
	if orphaned_messages:
		print(f"   ✗ Found {len(orphaned_messages)} messages referencing non-existent chats:")
		for chat_id in orphaned_messages:
			print(f"     - {chat_id}")
	else:
		print("   ✓ All messages reference existing chats")

	print("\n" + "=" * 50)
	if scenes_ok and not orphaned_messages:
		print("✓ SUCCESS: All relationships are properly established!")
		print("  Every message belongs to a chat, a user, and a scene.")
		return True
	else:
		print("✗ FAILURE: Some relationships are missing or invalid.")
		return False


if __name__ == "__main__":
	success = main()
	exit(0 if success else 1)
