import io
from unittest.mock import Mock

import pytest

from src.infrastructure.gateways.object_storage_gateway import MinioObjectStorageGateway, _parse_endpoint


@pytest.mark.unit
class TestMinioObjectStorageGateway:
	@pytest.fixture
	def data_client(self):
		return Mock()

	@pytest.fixture
	def url_client(self):
		return Mock()

	@pytest.fixture
	def gw(self, data_client, url_client):
		return MinioObjectStorageGateway(
			_data_client=data_client,
			_url_client=url_client,
			_bucket_public="scripulya-public",
			_bucket_private="scripulya-private",
			_public_endpoint="localhost:9000",
			_public_secure=False,
			_presign_expiry_seconds=900,
		)

	@pytest.mark.unit
	def test_parse_endpoint_strips_scheme(self):
		assert _parse_endpoint("https://minio:9000/") == ("minio:9000", True)
		assert _parse_endpoint("http://minio:9000") == ("minio:9000", False)
		assert _parse_endpoint("minio:9000") == ("minio:9000", None)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_ensure_buckets_creates_missing_and_sets_public_policy(self, gw, data_client):
		data_client.bucket_exists.return_value = False

		await gw.ensure_buckets()

		assert data_client.make_bucket.call_count == 2
		data_client.set_bucket_policy.assert_called_once()
		bucket_name = data_client.set_bucket_policy.call_args.args[0]
		assert bucket_name == "scripulya-public"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_ensure_buckets_idempotent_when_existing(self, gw, data_client):
		data_client.bucket_exists.return_value = True

		await gw.ensure_buckets()

		data_client.make_bucket.assert_not_called()
		data_client.set_bucket_policy.assert_called_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_upload_chooses_public_bucket(self, gw, data_client):
		data = io.BytesIO(b"abc")

		bucket, size = await gw.upload("cat/x.png", data, 3, "image/png", is_public=True)

		assert bucket == "scripulya-public"
		assert size == 3
		data_client.put_object.assert_called_once_with("scripulya-public", "cat/x.png", data, 3, "image/png")

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_upload_chooses_private_bucket(self, gw, data_client):
		bucket, _ = await gw.upload("cat/secret.png", io.BytesIO(b"x"), 1, "image/png", is_public=False)

		assert bucket == "scripulya-private"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_presigned_get_url_uses_public_endpoint_client(self, gw, data_client, url_client):
		url_client.presigned_get_object.return_value = "http://localhost:9000/signed"

		url = await gw.presigned_get_url("scripulya-private", "cat/x.png")

		assert url == "http://localhost:9000/signed"
		url_client.presigned_get_object.assert_called_once()
		data_client.presigned_get_object.assert_not_called()

	@pytest.mark.unit
	def test_public_url_is_plain_and_scheme_correct(self, gw):
		assert gw.public_url("scripulya-public", "cat/x.png") == "http://localhost:9000/scripulya-public/cat/x.png"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_object(self, gw, data_client):
		await gw.delete_object("scripulya-public", "cat/x.png")
		data_client.remove_object.assert_called_once_with("scripulya-public", "cat/x.png")
