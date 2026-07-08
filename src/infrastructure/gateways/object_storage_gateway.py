import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO

import anyio
from minio import Minio
from minio.error import S3Error

from src.application.ports import IObjectStorageGateway

logger = logging.getLogger(__name__)


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
	endpoint and is used only to *sign* presigned URLs client-side (it never
	connects). Signing over the public host is what makes the URLs valid for
	clients fetching directly from MinIO.
	"""

	_data_client: Minio
	_url_client: Minio
	_bucket_public: str
	_bucket_private: str
	_public_endpoint: str  # host[:port], no scheme
	_public_secure: bool
	_presign_expiry_seconds: int

	@classmethod
	def from_settings(cls, settings) -> "MinioObjectStorageGateway":
		internal_host, _ = _parse_endpoint(settings.MINIO_INTERNAL_ENDPOINT)
		public_host, scheme_secure = _parse_endpoint(settings.MINIO_PUBLIC_ENDPOINT)
		secure = settings.MINIO_SECURE if scheme_secure is None else scheme_secure

		creds = dict(
			access_key=settings.MINIO_ROOT_USER,
			secret_key=settings.MINIO_ROOT_PASSWORD,
			secure=secure,
		)
		return cls(
			_data_client=Minio(internal_host, **creds),
			_url_client=Minio(public_host, **creds),
			_bucket_public=settings.MINIO_BUCKET_PUBLIC,
			_bucket_private=settings.MINIO_BUCKET_PRIVATE,
			_public_endpoint=public_host,
			_public_secure=secure,
			_presign_expiry_seconds=settings.MINIO_PRESIGN_EXPIRY_SECONDS,
		)

	async def ensure_buckets(self) -> None:
		await anyio.to_thread.run_sync(self._ensure_buckets_sync)

	def _ensure_buckets_sync(self) -> None:
		for bucket in (self._bucket_public, self._bucket_private):
			try:
				if not self._data_client.bucket_exists(bucket):
					self._data_client.make_bucket(bucket)
					logger.info("Created MinIO bucket: %s", bucket)
			except S3Error as e:
				# Race-safe: another worker may have created it concurrently.
				if e.code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
					raise
				logger.debug("MinIO bucket already exists: %s (%s)", bucket, e.code)

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
		logger.debug("MinIO public bucket policy applied: %s", self._bucket_public)

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
		logger.info("Uploaded %s bytes to %s/%s", length, bucket, object_key)
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
		logger.info("Deleted object %s/%s", bucket, object_key)
