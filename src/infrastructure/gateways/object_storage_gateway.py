import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO

import anyio
from minio import Minio
from minio.error import S3Error

from src.infrastructure.logging.logger import Logger
from src.application.ports.media import IObjectStorageGateway

# MinIO's default region. Preset on both clients so the minio SDK's region
# lookup (triggered by presigned_get_object) short-circuits instead of making a
# network call to the client's endpoint — the _url_client's endpoint (the public
# host) is not reachable from inside the backend container, so a region lookup
# against it would fail and 500 the upload.
MINIO_DEFAULT_REGION = "us-east-1"


def _parse_endpoint(endpoint: str) -> tuple[str, bool | None]:
	"""Split a MinIO endpoint into ``(host[:port], secure)``.

	The minio client takes a bare ``host:port`` plus a separate ``secure`` flag.
	Accept an optional ``http(s)://`` prefix for convenience; when a scheme is
	given it overrides the ``MINIO_SECURE`` setting for that endpoint.
	"""
	secure: bool | None = None
	for scheme, scheme_secure in (("https://", True), ("http://", False)):
		if endpoint.startswith(scheme):
			secure = scheme_secure
			endpoint = endpoint[len(scheme) :]
			break
	return endpoint.rstrip("/"), secure


@dataclass
class MinioObjectStorageGateway(IObjectStorageGateway):
	"""MinIO/S3-backed object storage for media assets.

	Holds two clients: ``_data_client`` talks to the in-network data endpoint
	(uploads, bucket provisioning); ``_url_client`` is configured with the public
	endpoint and is used to *sign* presigned URLs over the public host so they are
	valid for clients fetching directly from MinIO. Both clients are constructed
	with a preset region so the SDK's region lookup (which presigned_get_object
	triggers) short-circuits instead of dialing the endpoint — the public host is
	not reachable from inside the backend container.
	"""

	_data_client: Minio
	_url_client: Minio
	_bucket_public: str
	_bucket_private: str
	_public_endpoint: str  # host[:port], no scheme
	_public_secure: bool
	_presign_expiry_seconds: int
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	@classmethod
	def from_settings(cls, settings, logger: logging.Logger) -> "MinioObjectStorageGateway":
		internal_host, _ = _parse_endpoint(settings.MINIO_INTERNAL_ENDPOINT)
		public_host, scheme_secure = _parse_endpoint(settings.MINIO_PUBLIC_ENDPOINT)
		secure = settings.MINIO_SECURE if scheme_secure is None else scheme_secure

		creds = dict(
			access_key=settings.MINIO_ROOT_USER,
			secret_key=settings.MINIO_ROOT_PASSWORD,
			secure=secure,
			region=MINIO_DEFAULT_REGION,
		)
		return cls(
			_data_client=Minio(internal_host, **creds),
			_url_client=Minio(public_host, **creds),
			_bucket_public=settings.MINIO_BUCKET_PUBLIC,
			_bucket_private=settings.MINIO_BUCKET_PRIVATE,
			_public_endpoint=public_host,
			_public_secure=secure,
			_presign_expiry_seconds=settings.MINIO_PRESIGN_EXPIRY_SECONDS,
			logger=logger,
		)

	async def ensure_buckets(self) -> None:
		await anyio.to_thread.run_sync(self._ensure_buckets_sync)

	def _ensure_buckets_sync(self) -> None:
		for bucket in (self._bucket_public, self._bucket_private):
			try:
				if not self._data_client.bucket_exists(bucket):
					self._data_client.make_bucket(bucket)
					self.logger.info("Created MinIO bucket: %s", bucket)
			except S3Error as e:
				# Race-safe: another worker may have created it concurrently.
				if e.code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
					raise
				self.logger.debug("MinIO bucket already exists: %s (%s)", bucket, e.code)

		# Anonymous read on the public bucket -> stable public URLs (no signature).
		policy = {
			"Version": "2012-10-17",
			"Statement": [
				{
					"Effect": "Allow",
					"Principal": {"AWS": ["*"]},
					"Action": ["s3:GetObject"],
					"Resource": [f"arn:aws:s3:::{self._bucket_public}/*"],
				}
			],
		}
		self._data_client.set_bucket_policy(self._bucket_public, json.dumps(policy))
		self.logger.debug("MinIO public bucket policy applied: %s", self._bucket_public)

	async def upload(
		self,
		object_key: str,
		data: BinaryIO,
		length: int,
		content_type: str,
		is_public: bool,
	) -> tuple[str, int]:
		bucket = self._bucket_public if is_public else self._bucket_private
		await anyio.to_thread.run_sync(self._data_client.put_object, bucket, object_key, data, length, content_type)
		self.logger.info("Uploaded %s bytes to %s/%s", length, bucket, object_key)
		return bucket, length

	async def presigned_get_url(self, bucket: str, object_key: str) -> str:
		url = await anyio.to_thread.run_sync(
			self._url_client.presigned_get_object,
			bucket,
			object_key,
			timedelta(seconds=self._presign_expiry_seconds),
		)
		return str(url)

	def public_url(self, bucket: str, object_key: str) -> str:
		scheme = "https" if self._public_secure else "http"
		return f"{scheme}://{self._public_endpoint}/{bucket}/{object_key}"

	async def delete_object(self, bucket: str, object_key: str) -> None:
		await anyio.to_thread.run_sync(self._data_client.remove_object, bucket, object_key)
		self.logger.info("Deleted object %s/%s", bucket, object_key)
