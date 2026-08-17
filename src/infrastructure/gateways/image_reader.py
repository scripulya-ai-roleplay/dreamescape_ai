import logging
from dataclasses import dataclass

from fastapi import UploadFile

from src.application.ports.media import IImageReader, UploadedImage
from src.infrastructure.exceptions import ImageTooLargeException, UnsupportedImageTypeException
from src.infrastructure.logging.logger import Logger

# Image content types accepted on upload. The extension is derived from the
# sniffed type (not the client-supplied filename) and doubles as the allowlist.
# image/svg+xml is intentionally NOT accepted: it is XML text that can carry an
# inline <script>, so an SVG served from the anonymous-readable public bucket is
# a stored-XSS vector. See _sniff_image_type.
_CONTENT_TYPE_EXT: dict[str, str] = {
	"image/png": "png",
	"image/jpeg": "jpg",
	"image/webp": "webp",
	"image/gif": "gif",
	"image/bmp": "bmp",
	"image/tiff": "tiff",
	"image/x-icon": "ico",
}

# Magic-number signatures used to determine the real type from the file bytes.
# The client-supplied Content-Type header is untrusted and must agree with this.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
	(b"\x89PNG\r\n\x1a\n", "image/png"),
	(b"\xff\xd8\xff", "image/jpeg"),
	(b"GIF87a", "image/gif"),
	(b"GIF89a", "image/gif"),
	(b"BM", "image/bmp"),
	(b"II*\x00", "image/tiff"),
	(b"MM\x00*", "image/tiff"),
	(b"\x00\x00\x01\x00", "image/x-icon"),
)

_READ_CHUNK = 64 * 1024


def _sniff_image_type(data: bytes | bytearray | memoryview) -> str | None:
	if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
		return "image/webp"
	for magic, content_type in _IMAGE_SIGNATURES:
		if data.startswith(magic):
			return content_type
	return None


@dataclass
class ImageReader(IImageReader):
	max_bytes: int
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def read(self, file: UploadFile) -> UploadedImage:
		content_type = (file.content_type or "").lower()

		buf = bytearray()
		while True:
			chunk = await file.read(_READ_CHUNK)
			if not chunk:
				break
			buf += chunk
			if len(buf) > self.max_bytes:
				self.logger.warning("Rejected upload: size exceeds %s bytes", self.max_bytes)
				raise ImageTooLargeException(f"Image exceeds the {self.max_bytes}-byte limit")

		return self._finalize(content_type, buf)

	async def read_bytes(self, data: bytes, content_type: str | None = None) -> UploadedImage:
		if len(data) > self.max_bytes:
			self.logger.warning("Rejected bytes: size exceeds %s bytes", self.max_bytes)
			raise ImageTooLargeException(f"Image exceeds the {self.max_bytes}-byte limit")

		declared = (content_type or "").split(";")[0].strip().lower()
		return self._finalize(declared, data)

	def _finalize(self, declared: str, data: bytes | bytearray) -> UploadedImage:
		sniffed = _sniff_image_type(data)
		if sniffed is None:
			self.logger.warning("Rejected image: bytes are not a recognized image type")
			raise UnsupportedImageTypeException("File contents are not a recognized image type")
		final = declared if declared in _CONTENT_TYPE_EXT else sniffed
		if sniffed != final:
			self.logger.warning("Rejected image: claimed %s but sniffed %s", final, sniffed)
			raise UnsupportedImageTypeException("File contents do not match the declared image content type")
		return UploadedImage(
			content_type=final,
			ext=_CONTENT_TYPE_EXT[final],
			data=bytes(data),
			size=len(data),
		)
