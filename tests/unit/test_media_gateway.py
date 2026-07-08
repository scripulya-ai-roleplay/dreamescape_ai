import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.gateways.media_gateway import MediaGateway
from src.domain.models import MediaAsset, MediaEntityType
from src.application.media.schemas import MediaFilterDTO
from src.application.ports import Page


@pytest.mark.unit
class TestMediaGateway:
	@pytest.fixture
	def mock_session(self):
		mock = AsyncMock(spec=AsyncSession)
		mock.execute = AsyncMock()
		mock.add = Mock()
		mock.flush = AsyncMock()
		mock.refresh = AsyncMock()
		return mock

	@pytest.fixture
	def media_gateway(self, mock_session):
		return MediaGateway(session=mock_session)

	@pytest.fixture
	def sample_model(self):
		m = Mock()
		m.id = uuid4()
		m.object_key = "character/abc.png"
		m.bucket = "scripulya-public"
		m.file_url = None
		m.content_type = "image/png"
		m.size_bytes = 123
		m.entity_type = "character"
		m.entity_id = uuid4()
		m.is_public = True
		m.owner_id = uuid4()
		m.created_at = None
		return m

	@pytest.fixture
	def sample_domain(self):
		return MediaAsset(
			object_key="character/new.png",
			content_type="image/png",
			entity_type=MediaEntityType.CHARACTER,
			entity_id=uuid4(),
			is_public=True,
			owner_id=uuid4(),
		)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_create_round_trips_domain(self, media_gateway, mock_session, sample_domain):
		await media_gateway.create(sample_domain)
		mock_session.add.assert_called_once()
		mock_session.flush.assert_awaited_once()
		mock_session.refresh.assert_awaited_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_success(self, media_gateway, mock_session, sample_model):
		mock_result = Mock()
		mock_result.scalar_one.return_value = sample_model
		mock_session.execute.return_value = mock_result

		result = await media_gateway.get_one(sample_model.id)

		assert result.id == sample_model.id
		assert result.object_key == sample_model.object_key
		assert result.entity_type == MediaEntityType.CHARACTER
		assert result.is_public is True

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_not_found_raises(self, media_gateway, mock_session):
		from sqlalchemy.exc import NoResultFound

		mock_result = Mock()
		mock_result.scalar_one.side_effect = NoResultFound()
		mock_session.execute.return_value = mock_result

		with pytest.raises(NoResultFound):
			await media_gateway.get_one(uuid4())

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_for_entity(self, media_gateway, mock_session, sample_model):
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_model]
		mock_result.scalars.return_value = mock_scalars
		mock_session.execute.return_value = mock_result

		result = await media_gateway.get_for_entity(MediaEntityType.SCENE, sample_model.entity_id)

		assert isinstance(result, list)
		assert len(result) == 1
		assert result[0].object_key == sample_model.object_key

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_applies_visibility_and_pagination(self, media_gateway, mock_session, sample_model):
		# search issues two executes: count, then items.
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_items_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_model]
		mock_items_result.scalars.return_value = mock_scalars
		mock_session.execute.side_effect = [mock_count_result, mock_items_result]

		dto = MediaFilterDTO(
			entity_type=MediaEntityType.CHARACTER, entity_id=sample_model.entity_id, limit=10, offset=0
		)
		result = await media_gateway.search(dto, actor_id=sample_model.owner_id)

		assert isinstance(result, Page)
		assert result.count == 1
		assert len(result.items) == 1
		# the executed query was built (two DB calls happened)
		assert mock_session.execute.await_count == 2

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete(self, media_gateway, mock_session):
		media_id = uuid4()
		await media_gateway.delete(media_id)
		mock_session.execute.assert_awaited_once()

	@pytest.mark.unit
	def test_to_domain_conversion(self, media_gateway, sample_model):
		result = media_gateway._to_domain(sample_model)

		assert result.id == sample_model.id
		assert result.bucket == sample_model.bucket
		assert result.entity_type == MediaEntityType.CHARACTER
		assert result.owner_id == sample_model.owner_id
