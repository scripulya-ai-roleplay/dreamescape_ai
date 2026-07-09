from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.application.ports import UploadedImage
from src.infrastructure.exceptions import ImageTooLargeException, UnsupportedImageTypeException
from src.infrastructure.gateways.image_reader import ImageReader, _sniff_image_type


class _FakeUpload(UploadFile):
	"""A fastapi.UploadFile backed by in-memory bytes (content_type via headers)."""

	def __init__(self, data: bytes, content_type: str = "image/png"):
		super().__init__(file=BytesIO(data), headers=Headers({"content-type": content_type}))


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # real PNG magic + dummy body
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32  # real JPEG magic + dummy body
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16
HTML_BYTES = b"<html><body><img src=x onerror=alert(1)></body></html>"


def _reader(max_bytes: int = 10 * 1024 * 1024) -> ImageReader:
	return ImageReader(max_bytes=max_bytes)


@pytest.mark.unit
class TestSniffImageType:
	@pytest.mark.parametrize(
		("data", "expected"),
		[
			(PNG_BYTES, "image/png"),
			(JPEG_BYTES, "image/jpeg"),
			(WEBP_BYTES, "image/webp"),
			(b"GIF89a" + b"\x00" * 10, "image/gif"),
			(b"BM" + b"\x00" * 10, "image/bmp"),
		],
	)
	def test_detects_known_types(self, data, expected):
		assert _sniff_image_type(data) == expected

	@pytest.mark.parametrize("data", [HTML_BYTES, b"<?xml version='1.0'?><svg/>", b"", b"not an image"])
	def test_rejects_non_images(self, data):
		assert _sniff_image_type(data) is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestImageReaderRead:
	async def test_reads_valid_png(self):
		image = await _reader().read(_FakeUpload(PNG_BYTES, "image/png"))
		assert isinstance(image, UploadedImage)
		assert image.content_type == "image/png"
		assert image.ext == "png"
		assert image.data == PNG_BYTES
		assert image.size == len(PNG_BYTES)

	async def test_rejects_unsupported_declared_type(self):
		# SVG is dropped from the allowlist entirely -> 415 before any sniffing.
		with pytest.raises(UnsupportedImageTypeException) as exc:
			await _reader().read(_FakeUpload(b"<svg onload=alert(1)></svg>", "image/svg+xml"))
		assert exc.value.status_code == 415

	async def test_rejects_sniff_vs_claim_mismatch(self):
		# Claims JPEG, ships PNG -> valid image, wrong type.
		with pytest.raises(UnsupportedImageTypeException) as exc:
			await _reader().read(_FakeUpload(PNG_BYTES, "image/jpeg"))
		assert exc.value.status_code == 415

	async def test_rejects_non_image_bytes(self):
		# Claims PNG, ships HTML -> sniff must catch the lie.
		with pytest.raises(UnsupportedImageTypeException) as exc:
			await _reader().read(_FakeUpload(HTML_BYTES, "image/png"))
		assert exc.value.status_code == 415

	async def test_rejects_oversize(self):
		# Cap smaller than payload -> 413 during the streaming read.
		big = PNG_BYTES + b"\x00" * 100
		with pytest.raises(ImageTooLargeException) as exc:
			await _reader(max_bytes=10).read(_FakeUpload(big, "image/png"))
		assert exc.value.status_code == 413
