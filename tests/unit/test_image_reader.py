from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.application.ports.media import UploadedImage
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
		with pytest.raises(UnsupportedImageTypeException) as exc:
			await _reader().read(_FakeUpload(b"<svg onload=alert(1)></svg>", "image/svg+xml"))
		assert exc.value.status_code == 415

	async def test_falls_back_to_sniff_when_part_has_no_content_type(self):
		image = await _reader().read(_FakeUpload(PNG_BYTES, ""))
		assert image.content_type == "image/png"

	async def test_falls_back_to_sniff_for_nonstandard_subtype(self):
		image = await _reader().read(_FakeUpload(PNG_BYTES, "image/jpg"))
		assert image.content_type == "image/png"

	async def test_rejects_sniffable_image_with_lied_about_content_type(self):
		with pytest.raises(UnsupportedImageTypeException) as exc:
			await _reader().read(_FakeUpload(PNG_BYTES, "image/jpeg"))
		assert exc.value.status_code == 415

	async def test_parameter_suffix_cannot_bypass_declared_type_check(self):
		with pytest.raises(UnsupportedImageTypeException) as exc:
			await _reader().read(_FakeUpload(JPEG_BYTES, "image/png; charset=utf-8"))
		assert exc.value.status_code == 415

	async def test_strips_content_type_parameters(self):
		image = await _reader().read(_FakeUpload(PNG_BYTES, "Image/PNG; charset=binary"))
		assert image.content_type == "image/png"

	async def test_rejects_non_image_bytes(self):
		with pytest.raises(UnsupportedImageTypeException) as exc:
			await _reader().read(_FakeUpload(HTML_BYTES, "image/png"))
		assert exc.value.status_code == 415

	async def test_rejects_non_image_bytes_before_reading_whole_body(self):
		file = _FakeUpload(HTML_BYTES + PNG_BYTES * 1000, "image/png")
		file.read = AsyncMock(wraps=file.read)
		with pytest.raises(UnsupportedImageTypeException):
			await _reader().read(file)
		assert file.read.await_count == 1

	async def test_rejects_oversize(self):
		# Cap smaller than payload -> 413 during the streaming read.
		big = PNG_BYTES + b"\x00" * 100
		with pytest.raises(ImageTooLargeException) as exc:
			await _reader(max_bytes=10).read(_FakeUpload(big, "image/png"))
		assert exc.value.status_code == 413


@pytest.mark.unit
@pytest.mark.asyncio
class TestImageReaderReadBytes:
	async def test_reads_png_without_content_type(self):
		image = await _reader().read_bytes(PNG_BYTES)
		assert image.content_type == "image/png"
		assert image.ext == "png"
		assert image.data == PNG_BYTES

	async def test_strips_content_type_parameters(self):
		image = await _reader().read_bytes(PNG_BYTES, "image/png; charset=utf-8")
		assert image.content_type == "image/png"

	async def test_falls_back_to_sniff_for_nonstandard_subtype(self):
		image = await _reader().read_bytes(PNG_BYTES, "image/jpg")
		assert image.content_type == "image/png"

	async def test_rejects_known_subtype_mismatch(self):
		with pytest.raises(UnsupportedImageTypeException):
			await _reader().read_bytes(PNG_BYTES, "image/jpeg")

	async def test_rejects_non_image_bytes(self):
		with pytest.raises(UnsupportedImageTypeException):
			await _reader().read_bytes(HTML_BYTES, "image/png")

	async def test_rejects_oversize(self):
		big = PNG_BYTES + b"\x00" * 100
		with pytest.raises(ImageTooLargeException):
			await _reader(max_bytes=10).read_bytes(big, "image/png")
