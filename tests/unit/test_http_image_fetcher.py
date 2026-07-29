import socket

import httpx
import pytest

from src.infrastructure.gateways.http_image_fetcher import (
	HttpImageFetcher,
	UnsafeTargetException,
	_SSRFSafeTransport,
)


@pytest.mark.unit
class TestSSRFGuard:
	@pytest.mark.parametrize(
		"host",
		[
			"127.0.0.1",
			"10.0.0.1",
			"172.16.0.1",
			"192.168.1.1",
			"169.254.169.254",
			"0.0.0.0",
			"100.64.0.1",
			"::1",
			"fe80::1",
			"fc00::1",
		],
	)
	def test_rejects_non_public_ip_literals(self, host):
		with pytest.raises(UnsafeTargetException):
			HttpImageFetcher._resolve_safe(host)

	@pytest.mark.parametrize("host", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
	def test_returns_public_ip_literals(self, host):
		assert HttpImageFetcher._resolve_safe(host) == host

	def test_rejects_hostname_resolving_to_private(self, monkeypatch):
		monkeypatch.setattr(
			socket,
			"getaddrinfo",
			lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))],
		)
		with pytest.raises(UnsafeTargetException):
			HttpImageFetcher._resolve_safe("internal.example.com")

	def test_pins_resolved_public_ip(self, monkeypatch):
		monkeypatch.setattr(
			socket,
			"getaddrinfo",
			lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
		)
		assert HttpImageFetcher._resolve_safe("example.com") == "93.184.216.34"

	def test_rejects_hostname_with_any_private_address(self, monkeypatch):
		monkeypatch.setattr(
			socket,
			"getaddrinfo",
			lambda *a, **k: [
				(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
				(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
			],
		)
		with pytest.raises(UnsafeTargetException):
			HttpImageFetcher._resolve_safe("rebind.example.com")

	def test_unresolvable_hostname_rejected(self, monkeypatch):
		monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("nope")))
		with pytest.raises(UnsafeTargetException):
			HttpImageFetcher._resolve_safe("does-not-exist.example.com")


@pytest.mark.unit
@pytest.mark.asyncio
class TestSSRFSafeTransportPinning:
	async def test_connects_to_pinned_ip_with_original_host_and_sni(self, monkeypatch):
		captured: dict = {}

		async def fake_handle(self, request: httpx.Request) -> httpx.Response:
			captured["url_host"] = request.url.host
			captured["url_port"] = request.url.port
			captured["host_header"] = request.headers.get("host")
			captured["sni"] = request.extensions.get("sni_hostname")
			return httpx.Response(200)

		monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)
		monkeypatch.setattr(
			socket,
			"getaddrinfo",
			lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
		)

		transport = _SSRFSafeTransport()
		await transport.handle_async_request(httpx.Request("GET", "https://example.com:8443/path?q=1"))

		assert captured["url_host"] == "93.184.216.34"
		assert captured["url_port"] == 8443
		assert captured["host_header"] == "example.com:8443"
		assert captured["sni"] == "example.com"

	async def test_raises_before_connect_when_host_is_private(self, monkeypatch):
		async def fail_handle(self, request: httpx.Request) -> httpx.Response:
			pytest.fail("transport must not connect to an unsafe host")

		monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fail_handle)
		transport = _SSRFSafeTransport()
		with pytest.raises(UnsafeTargetException):
			await transport.handle_async_request(httpx.Request("GET", "http://169.254.169.254/x"))
