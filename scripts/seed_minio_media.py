#!/usr/bin/env python3
"""Seed anime-style scene background images into MinIO on dev setup.

Runs as the ``minio-init`` sidecar (``scripulya_deploy/docker-compose.yml``). For every
scene that has a ``media_assets`` row (``entity_type='scene'``), it generates an anime
background from the scene's ``background_prompt`` via Google Imagen and uploads it to the
public MinIO bucket at the row's ``object_key``.

``init.sql`` is the single source of truth: the prompt comes from ``scenes.background_prompt``
and the target path from ``media_assets.object_key`` — this script never duplicates either,
so adding/changing a scene image is a one-file edit in ``init.sql``.

Idempotent: objects already present are skipped unless ``FORCE_REGENERATE_MEDIA=1``, so it
only spends API quota when the MinIO volume is fresh (``make reseed``) or when forced.

Best-effort: a missing API key logs a warning and exits 0 (the app still runs, just without
seeded art); a per-scene failure is logged and skipped. Only infrastructure errors (DB or
MinIO unreachable) exit non-zero.
"""

from __future__ import annotations

import io
import json
import logging
import os
from dataclasses import dataclass

import psycopg2
from google import genai
from google.genai import types as gtypes
from minio import Minio
from minio.error import S3Error

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed-minio-media")


# Anonymous read on the public bucket -> stable public URLs (no signature). Mirrors
# MinioObjectStorageGateway._ensure_buckets_sync in src/infrastructure/gateways/
# object_storage_gateway.py so seeding works even before the backend has started.
def _public_read_policy(bucket: str) -> str:
	return json.dumps(
		{
			"Version": "2012-10-17",
			"Statement": [
				{
					"Effect": "Allow",
					"Principal": {"AWS": ["*"]},
					"Action": ["s3:GetObject"],
					"Resource": [f"arn:aws:s3:::{bucket}/*"],
				}
			],
		}
	)


@dataclass
class Settings:
	database_url: str
	minio_endpoint: str  # host[:port], no scheme
	minio_secure: bool
	minio_access_key: str
	minio_secret_key: str
	bucket_public: str
	image_api_key: str
	image_api_model: str
	force: bool


def _truthy(value: str | None) -> bool:
	return str(value or "").lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
	# MinIO endpoint may carry an http(s):// prefix; the minio client takes a bare host.
	endpoint = os.environ.get("MINIO_INTERNAL_ENDPOINT", "minio:9000")
	secure = _truthy(os.environ.get("MINIO_SECURE"))
	for scheme in ("https://", "http://"):
		if endpoint.startswith(scheme):
			secure = scheme == "https://"
			endpoint = endpoint[len(scheme) :]
			break
	endpoint = endpoint.rstrip("/")

	# IMAGE_API_KEY falls back to GEMINI_API_KEY (the agent already uses Gemini for LLM).
	image_api_key = os.environ.get("IMAGE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""

	return Settings(
		database_url=os.environ.get("DATABASE_URL", "postgresql+asyncpg://user:password@postgres:5432/dbname"),
		minio_endpoint=endpoint,
		minio_secure=secure,
		minio_access_key=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
		minio_secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
		bucket_public=os.environ.get("MINIO_BUCKET_PUBLIC", "scripulya-public"),
		image_api_key=image_api_key,
		image_api_model=os.environ.get("IMAGE_API_MODEL", "imagen-4.0-generate-001"),
		force=_truthy(os.environ.get("FORCE_REGENERATE_MEDIA")),
	)


def _psycopg_dsn(database_url: str) -> str:
	# The app's DATABASE_URL uses the asyncpg driver; psycopg2 wants its own scheme.
	for driver in ("+asyncpg", "+psycopg", "+psycopg2"):
		if driver in database_url:
			return database_url.replace(driver, "")
	return database_url


def fetch_scene_targets(settings: Settings) -> list[dict]:
	"""One row per scene that should get a background image.

	prompt and object_key both come from the DB (init.sql is the source of truth).
	"""
	query = """
		SELECT s.title, s.background_prompt, m.object_key, m.id::text
		FROM scenes s
		JOIN media_assets m
		  ON m.entity_id = s.id AND m.entity_type = 'scene'
		WHERE m.object_key IS NOT NULL
		ORDER BY s.title
	"""
	with psycopg2.connect(_psycopg_dsn(settings.database_url)) as conn, conn.cursor() as cur:
		cur.execute(query)
		cols = [c[0] for c in cur.description]
		return [dict(zip(cols, row)) for row in cur.fetchall()]


def ensure_public_bucket(client: Minio, bucket: str) -> None:
	if not client.bucket_exists(bucket):
		client.make_bucket(bucket)
		log.info("Created MinIO bucket: %s", bucket)
	try:
		client.set_bucket_policy(bucket, _public_read_policy(bucket))
	except S3Error as e:  # pragma: no cover - defensive
		log.warning("Could not set public-read policy on %s: %s", bucket, e)


def object_exists(client: Minio, bucket: str, object_key: str) -> bool:
	try:
		client.stat_object(bucket, object_key)
		return True
	except S3Error as e:
		if e.code in ("NoSuchKey", "NoSuchObject"):
			return False
		raise


def build_prompt(title: str, background_prompt: str) -> str:
	return (
		"Anime-style background illustration, atmospheric, cinematic lighting, "
		"wide landscape, highly detailed, no people, no characters, no faces, "
		f"no text, no watermark, no logos. Scene: {title}. {background_prompt}"
	)


def generate_image(gen_client: genai.Client, model: str, title: str, background_prompt: str) -> bytes:
	prompt = build_prompt(title, background_prompt)
	resp = gen_client.models.generate_images(
		model=model,
		prompt=prompt,
		config=gtypes.GenerateImagesConfig(
			number_of_images=1,
			aspect_ratio="16:9",
			output_mime_type="image/png",
			# NOTE: negative_prompt is unsupported on the Gemini Developer API (API-key)
			# path — Enterprise-only — so the "no people/text" guidance lives in the
			# positive prompt above instead.
		),
	)
	if not resp.generated_images:
		raise RuntimeError("image model returned no images")
	return resp.generated_images[0].image.image_bytes


def update_size_bytes(settings: Settings, media_id: str, size_bytes: int) -> None:
	dsn = _psycopg_dsn(settings.database_url)
	with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
		cur.execute(
			"UPDATE media_assets SET size_bytes = %s, content_type = 'image/png' WHERE id = %s::uuid",
			(size_bytes, media_id),
		)
	conn.close()


def main() -> int:
	settings = load_settings()

	if not settings.image_api_key:
		log.warning(
			"IMAGE_API_KEY (or GEMINI_API_KEY) is not set — skipping scene image generation. "
			"The app still runs; set it in scripulya_deploy/.env to populate scene art."
		)
		return 0

	# Infrastructure setup: these errors are worth surfacing (exit 1).
	minio_client = Minio(
		settings.minio_endpoint,
		access_key=settings.minio_access_key,
		secret_key=settings.minio_secret_key,
		secure=settings.minio_secure,
	)
	ensure_public_bucket(minio_client, settings.bucket_public)
	gen_client = genai.Client(api_key=settings.image_api_key)
	targets = fetch_scene_targets(settings)

	if not targets:
		log.warning("No scene media_assets rows with an object_key found — nothing to seed.")
		return 0

	log.info(
		"Seeding %d scene image(s) into bucket '%s' (model=%s, force=%s).",
		len(targets),
		settings.bucket_public,
		settings.image_api_model,
		settings.force,
	)

	uploaded = skipped = failed = 0
	for row in targets:
		object_key = row["object_key"]
		label = f"{object_key} ({row['title']})"
		try:
			if not settings.force and object_exists(minio_client, settings.bucket_public, object_key):
				log.info("skip (exists): %s", label)
				skipped += 1
				continue
			data = generate_image(gen_client, settings.image_api_model, row["title"], row["background_prompt"])
			minio_client.put_object(
				settings.bucket_public, object_key, io.BytesIO(data), length=len(data), content_type="image/png"
			)
			update_size_bytes(settings, row["id"], len(data))
			log.info("uploaded: %s (%d bytes)", label, len(data))
			uploaded += 1
		except Exception as exc:  # per-scene failure must not abort the rest
			log.error("failed: %s -> %s", label, exc)
			failed += 1

	log.info("Done: %d uploaded, %d skipped, %d failed.", uploaded, skipped, failed)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except (psycopg2.OperationalError, S3Error) as exc:
		log.error("Infrastructure error (is postgres/MinIO up?): %s", exc)
		raise SystemExit(1)
