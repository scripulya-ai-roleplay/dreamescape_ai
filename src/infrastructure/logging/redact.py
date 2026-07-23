def preview(value: str | None, max_words: int = 10) -> str:
	if not value:
		return ""
	words = value.split()
	head = " ".join(words[:max_words])
	return head + ("…" if len(words) > max_words else "")
