import socket

import pytest

from src.infrastructure.gateways.http_image_fetcher import HttpImageFetcher, UnsafeTargetException


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
			HttpImageFetcher._assert_safe_host(host)

	@pytest.mark.parametrize("host", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
	def test_allows_public_ip_literals(self, host):
		HttpImageFetcher._assert_safe_host(host)

	def test_rejects_hostname_resolving_to_private(self, monkeypatch):
		monkeypatch.setattr(
			socket,
			"getaddrinfo",
			lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))],
		)
		with pytest.raises(UnsafeTargetException):
			HttpImageFetcher._assert_safe_host("internal.example.com")

	def test_allows_hostname_resolving_to_public(self, monkeypatch):
		monkeypatch.setattr(
			socket,
			"getaddrinfo",
			lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
		)
		HttpImageFetcher._assert_safe_host("example.com")

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
			HttpImageFetcher._assert_safe_host("rebind.example.com")

	def test_unresolvable_hostname_rejected(self, monkeypatch):
		monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("nope")))
		with pytest.raises(UnsafeTargetException):
			HttpImageFetcher._assert_safe_host("does-not-exist.example.com")
