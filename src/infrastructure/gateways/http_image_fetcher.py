import ipaddress
import logging
import socket
from dataclasses import dataclass

import anyio
import httpx

from src.application.ports.imports import FetchedImage, IImageFetcher
from src.infrastructure.logging.logger import Logger


class UnsafeTargetException(Exception):
	pass


class _SSRFSafeTransport(httpx.AsyncHTTPTransport):
	async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
		url = request.url
		scheme = (url.scheme or "").lower()
		host = url.host
		if scheme not in ("http", "https") or not host:
			raise UnsafeTargetException(f"Refused unsafe target scheme={scheme!r} host={host!r}")

		pinned_ip = await anyio.to_thread.run_sync(HttpImageFetcher._resolve_safe, host)
		authority = url.netloc.decode("ascii")
		request.url = url.copy_with(host=pinned_ip)
		request.headers["host"] = authority
		request.extensions["sni_hostname"] = host
		return await super().handle_async_request(request)


@dataclass
class HttpImageFetcher(IImageFetcher):
	max_bytes: int
	timeout: float = 15.0
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)
	_client: httpx.AsyncClient | None = None

	async def fetch(self, url: str) -> FetchedImage | None:
		try:
			client = self._ensure_client()
			async with client.stream("GET", url) as response:
				response.raise_for_status()
				content_type = response.headers.get("content-type")
				buf = bytearray()
				async for chunk in response.aiter_bytes():
					buf += chunk
					if len(buf) > self.max_bytes:
						self.logger.warning("Image %s exceeds %s bytes; skipping", url, self.max_bytes)
						return None
				if not buf:
					return None
				return FetchedImage(data=bytes(buf), content_type=content_type)
		except Exception as exc:
			self.logger.warning("Failed to fetch image %s: %s", url, exc)
			return None

	async def aclose(self) -> None:
		if self._client is not None:
			await self._client.aclose()
			self._client = None

	def _ensure_client(self) -> httpx.AsyncClient:
		if self._client is None:
			self._client = httpx.AsyncClient(
				timeout=self.timeout,
				follow_redirects=True,
				transport=_SSRFSafeTransport(),
			)
		return self._client

	@staticmethod
	def _resolve_safe(host: str) -> str:
		try:
			addr = ipaddress.ip_address(host)
		except ValueError:
			pass
		else:
			if not addr.is_global:
				raise UnsafeTargetException(f"Refused non-public host {host}")
			return str(addr)

		try:
			infos = socket.getaddrinfo(host, None)
		except socket.gaierror as exc:
			raise UnsafeTargetException(f"Could not resolve host {host}: {exc}") from exc

		for info in infos:
			addr = ipaddress.ip_address(info[4][0])
			if not addr.is_global:
				raise UnsafeTargetException(f"Refused host {host}: resolves to non-public {addr}")

		return infos[0][4][0]
