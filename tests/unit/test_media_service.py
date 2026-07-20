from io import BytesIO
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from src.application.authz import AuthorizationService
from src.application.media.schemas import MediaFilterDTO, MediaUploadDTO
from src.application.media.service import MediaService
from src.application.ports import UploadedImage
from src.domain.models import MediaAsset, MediaEntityType


class _FakeUpload(UploadFile):
	"""A fastapi.UploadFile stand-in; only its existence matters here (the reader
	is mocked, so the file is never actually read)."""

	def __init__(self, data: bytes = b"", content_type: str = "image/png"):
		super().__init__(file=BytesIO(data), headers=Headers({"content-type": content_type}))


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _service(*, storage=None, gateway=None, reader=None, uow=None):
	return MediaService(
		storage=storage or AsyncMock(),
		gateway=gateway or AsyncMock(),
		reader=reader or AsyncMock(),
		uow=uow or AsyncMock(),
		authz=AuthorizationService(),
	)


def _upload(owner_id: UUID, *, is_public: bool = True) -> MediaUploadDTO:
	return MediaUploadDTO(
		file=_FakeUpload(PNG_BYTES, "image/png"),
		entity_type=MediaEntityType.CHARACTER,
		entity_id=uuid4(),
		is_public=is_public,
		owner_id=owner_id,
	)


@pytest.mark.unit
class TestMediaFilterDTOLimit:
	def test_limit_zero_is_allowed(self):
		dto = MediaFilterDTO(limit=0)
		assert dto.limit == 0

	def test_limit_above_cap_rejected(self):
		with pytest.raises(ValidationError):
			MediaFilterDTO(limit=201)

	def test_limit_negative_rejected(self):
		with pytest.raises(ValidationError):
			MediaFilterDTO(limit=-1)


@pytest.mark.unit
@pytest.mark.asyncio
class TestMediaServiceUpload:
	"""Orchestration only — the byte-level read/validation is the reader's job
	(see test_image_reader.py); here it is mocked."""

	@pytest.fixture
	def owner_id(self):
		return uuid4()

	@pytest.fixture
	def gateway(self, owner_id):
		gw = AsyncMock()
		# By default the uploader owns the entity (ownership check passes).
		gw.get_entity_owner.return_value = owner_id
		gw.create.return_value = MediaAsset(
			id=uuid4(),
			object_key="character/abc.png",
			bucket="scripulya-public",
			content_type="image/png",
			entity_type=MediaEntityType.CHARACTER,
			entity_id=uuid4(),
			is_public=True,
			owner_id=owner_id,
		)
		return gw

	@pytest.fixture
	def storage(self):
		st = AsyncMock()
		st.upload.return_value = ("scripulya-public", len(PNG_BYTES))
		# public_url is a sync method returning a string (not a coroutine).
		st.public_url = Mock(return_value="http://test/scripulya-public/character/abc.png")
		return st

	@pytest.fixture
	def reader(self):
		rd = AsyncMock()
		rd.read.return_value = UploadedImage(content_type="image/png", ext="png", data=PNG_BYTES, size=len(PNG_BYTES))
		return rd

	async def test_happy_path(self, gateway, storage, reader, owner_id):
		svc = _service(storage=storage, gateway=gateway, reader=reader)
		dto = await svc.upload(_upload(owner_id))
		assert dto.content_type == "image/png"
		reader.read.assert_awaited_once()
		storage.upload.assert_awaited_once()
		gateway.create.assert_awaited_once()

	async def test_rejects_non_owner(self, gateway, storage, reader, owner_id):
		gateway.get_entity_owner.return_value = uuid4()  # someone else owns it
		svc = _service(storage=storage, gateway=gateway, reader=reader)
		with pytest.raises(HTTPException) as exc:
			await svc.upload(_upload(owner_id))
		assert exc.value.status_code == 403
		reader.read.assert_not_awaited()  # authorization fails before the file is read
		storage.upload.assert_not_awaited()
		gateway.create.assert_not_awaited()

	async def test_rejects_missing_entity(self, gateway, storage, reader, owner_id):
		gateway.get_entity_owner.return_value = None  # entity does not exist
		svc = _service(storage=storage, gateway=gateway, reader=reader)
		with pytest.raises(HTTPException) as exc:
			await svc.upload(_upload(owner_id))
		assert exc.value.status_code == 403  # 403, not 404, to avoid leaking existence
		reader.read.assert_not_awaited()

	async def test_cleans_up_object_on_db_failure(self, gateway, storage, reader, owner_id):
		gateway.create.side_effect = RuntimeError("db down")
		svc = _service(storage=storage, gateway=gateway, reader=reader)

		with pytest.raises(RuntimeError):
			await svc.upload(_upload(owner_id))
		# The object was uploaded, then reclaimed because the DB write failed.
		storage.upload.assert_awaited_once()
		storage.delete_object.assert_awaited_once()
		args, _ = storage.delete_object.call_args
		assert args[0] == "scripulya-public"
		assert args[1].startswith("character/") and args[1].endswith(".png")
