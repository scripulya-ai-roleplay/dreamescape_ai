import tiktoken

from src.application.ports.llm import ITokenCounter


class TiktokenTokenCounter(ITokenCounter):
	def __init__(self, encoding_name: str = "o200k_base") -> None:
		self._encoding = tiktoken.get_encoding(encoding_name)

	def count(self, text: str) -> int:
		return len(self._encoding.encode_ordinary(text))
