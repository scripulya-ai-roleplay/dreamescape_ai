import logging
from dataclasses import dataclass

from fastapi import UploadFile

from src.application.ports import IImageReader, UploadedImage
from src.infrastructure.exceptions import ImageTooLargeException, UnsupportedImageTypeException

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
	"""Return the image content type implied by the leading bytes, or ``None``.

	Used to validate the client-claimed Content-Type against the actual payload
	so a browser cannot be tricked into rendering a hostile type (e.g. HTML/SVG)
	under an image label.
	"""
	if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
		return "image/webp"
	for magic, content_type in _IMAGE_SIGNATURES:
		if data.startswith(magic):
			return content_type
	return None


@dataclass
class ImageReader(IImageReader):
	"""Reads and validates an uploaded image: enforces the size cap and verifies
	the real content type via magic-number sniffing. Keeps byte-level upload
	parsing out of the media service (single responsibility).
	"""

	max_bytes: int
	logger: logging.Logger

	async def read(self, file: UploadFile) -> UploadedImage:
		content_type = (file.content_type or "").lower()
		if content_type not in _CONTENT_TYPE_EXT:
			self.logger.warning("Rejected upload: unsupported content_type=%s", content_type)
			raise UnsupportedImageTypeException(f"Unsupported image content type: {content_type or 'unknown'}")

		# Stream into memory with a hard cap so a huge upload cannot OOM the process.
		buf = bytearray()
		while True:
			chunk = await file.read(_READ_CHUNK)
			if not chunk:
				break
			buf += chunk
			if len(buf) > self.max_bytes:
				self.logger.warning("Rejected upload: size exceeds %s bytes", self.max_bytes)
				raise ImageTooLargeException(f"Image exceeds the {self.max_bytes}-byte limit")

		# The header is trivially forged, so the magic number is the source of truth.
		sniffed = _sniff_image_type(buf)
		if sniffed is None or sniffed != content_type:
			self.logger.warning(
				"Rejected upload: bytes do not match claimed type %s (sniffed=%s)", content_type, sniffed
			)
			raise UnsupportedImageTypeException("File contents do not match the declared image content type")

		return UploadedImage(
			content_type=content_type,
			ext=_CONTENT_TYPE_EXT[content_type],
			data=bytes(buf),
			size=len(buf),
		)
