#!/usr/bin/env python3
"""Seed anime-style scene backgrounds and character portraits into MinIO on dev setup.

Runs as the ``minio-init`` sidecar (``scripulya_deploy/docker-compose.yml``). For every
``media_assets`` row that carries an ``object_key`` it generates an anime image via Google
Imagen and uploads it to the public MinIO bucket: wide 16:9 landscapes for scenes
(``entity_type='scene'``, prompt from ``background_prompt``) and 1:1 head-and-shoulders
portraits for characters (``entity_type='character'``, prompt from ``system_prompt``).

``init.sql`` is the single source of truth: the prompt comes from ``scenes.background_prompt``
or ``characters.system_prompt`` and the target path from ``media_assets.object_key`` — this
script never duplicates either, so adding/changing a seeded image is a one-file edit in
``init.sql``.

Idempotent: objects already present are skipped unless ``FORCE_REGENERATE_MEDIA=1``, so it
only spends API quota when the MinIO volume is fresh (``make reseed``) or when forced.

Offline cache (``MEDIA_BACKUP_DIR``): when set, a generated image is also written to
``$MEDIA_BACKUP_DIR/<object_key>`` and, on later runs, re-uploaded from there instead of
calling the image API. This is what makes ``make up`` after a ``docker compose down -v``
free: the host-mounted ``media-backup/`` survives the volume wipe, so the seeder restores
the PNGs without spending any quota. ``FORCE_REGENERATE_MEDIA=1`` bypasses the cache on read
(but still writes through) so ``make regen-media`` stays a true regeneration.

Best-effort: a missing API key logs a warning and exits 0 (the app still runs, just without
seeded art); a per-image failure is logged and skipped. Only infrastructure errors (DB or
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
	backup_dir: str | None  # host dir of pre-generated PNGs; None disables the offline cache


@dataclass
class MediaTarget:
	"""One image to generate and upload.

	prompt and object_key both come from the DB (init.sql is the source of truth);
	aspect_ratio is fixed per entity kind (16:9 scene landscapes, 1:1 character portraits).
	"""

	id: str  # media_assets.id — backfilled into size_bytes after upload
	object_key: str
	label: str  # human-readable, for logs ("scene/x.png (Title)")
	prompt: str
	aspect_ratio: str


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
		backup_dir=os.environ.get("MEDIA_BACKUP_DIR") or None,
	)


def _psycopg_dsn(database_url: str) -> str:
	# The app's DATABASE_URL uses the asyncpg driver; psycopg2 wants its own scheme.
	for driver in ("+asyncpg", "+psycopg", "+psycopg2"):
		if driver in database_url:
			return database_url.replace(driver, "")
	return database_url


def fetch_scene_targets(settings: Settings) -> list[MediaTarget]:
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
		return [
			MediaTarget(
				id=row[3],
				object_key=row[2],
				label=f"{row[2]} ({row[0]})",
				prompt=build_scene_prompt(row[0], row[1] or ""),
				aspect_ratio="16:9",
			)
			for row in cur.fetchall()
		]


def fetch_character_targets(settings: Settings) -> list[MediaTarget]:
	"""One MediaTarget per character that should get a portrait (1:1).

	prompt is built from the character's name + system_prompt; object_key from init.sql.
	"""
	query = """
		SELECT c.name, c.system_prompt, m.object_key, m.id::text
		FROM characters c
		JOIN media_assets m
			ON m.entity_id = c.id AND m.entity_type = 'character'
		WHERE m.object_key IS NOT NULL
		ORDER BY c.name
	"""
	with psycopg2.connect(_psycopg_dsn(settings.database_url)) as conn, conn.cursor() as cur:
		cur.execute(query)
		return [
			MediaTarget(
				id=row[3],
				object_key=row[2],
				label=f"{row[2]} ({row[0]})",
				prompt=build_character_prompt(row[0], row[1] or ""),
				aspect_ratio="1:1",
			)
			for row in cur.fetchall()
		]


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


def _read_cache(backup_dir: str | None, object_key: str) -> bytes | None:
	"""Return cached image bytes for ``object_key``, or None if no backup dir / no cached file.

	A read error degrades to a cache miss (mirrors _write_cache) so the scene still generates via the API.
	"""
	if not backup_dir:
		return None
	path = os.path.join(backup_dir, object_key)
	if not os.path.isfile(path):
		return None
	try:
		with open(path, "rb") as fh:
			return fh.read()
	except OSError as exc:
		log.warning("could not read cache %s: %s", object_key, exc)
		return None


def _write_cache(backup_dir: str | None, object_key: str, data: bytes) -> None:
	"""Persist a freshly generated image so future seeds skip the API call.

	Caching is an optimization, not a requirement: a write failure is logged and swallowed
	(the image is still uploaded to MinIO for this run).
	"""
	if not backup_dir:
		return
	path = os.path.join(backup_dir, object_key)
	tmp_path = f"{path}.tmp"
	try:
		os.makedirs(os.path.dirname(path), exist_ok=True)
		# Write a sibling .tmp then atomically rename, so an interrupt can't leave a
		# half-written file the next run would read back as a corrupt image.
		with open(tmp_path, "wb") as fh:
			fh.write(data)
		os.replace(tmp_path, path)
	except OSError as exc:
		log.warning("could not cache %s: %s", object_key, exc)
		try:
			os.remove(tmp_path)
		except OSError:
			pass


def build_scene_prompt(title: str, background_prompt: str) -> str:
	return (
		"Anime-style background illustration, atmospheric, cinematic lighting, "
		"wide landscape, highly detailed, no people, no characters, no faces, "
		f"no text, no watermark, no logos. Scene: {title}. {background_prompt}"
	)


def build_character_prompt(name: str, system_prompt: str) -> str:
	# system_prompt describes personality rather than appearance, so we frame it as a
	# portrait of "a character who is …" and let the model imagine a fitting look.
	return (
		"Anime-style character portrait, head and shoulders, centered, expressive face, "
		"highly detailed, soft simple background, no text, no watermark, no logos. "
		f"Character: {name}. {system_prompt}"
	)


def generate_image(gen_client: genai.Client, model: str, target: MediaTarget) -> bytes:
	resp = gen_client.models.generate_images(
		model=model,
		prompt=target.prompt,
		config=gtypes.GenerateImagesConfig(
			number_of_images=1,
			aspect_ratio=target.aspect_ratio,
			output_mime_type="image/png",
			# NOTE: negative_prompt is unsupported on the Gemini Developer API (API-key)
			# path — Enterprise-only — so the "no people/text" guidance lives in the
			# positive prompt instead.
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

	if not settings.image_api_key and not settings.backup_dir:
		log.warning(
			"IMAGE_API_KEY (or GEMINI_API_KEY) is not set and MEDIA_BACKUP_DIR is not configured — "
			"nothing to seed. The app still runs; set a key (to generate) or a backup dir (to restore)."
		)
		return 0
	if not settings.image_api_key:
		log.warning(
			"IMAGE_API_KEY (or GEMINI_API_KEY) is not set — restoring from the MEDIA_BACKUP_DIR cache "
			"only; any scene without a cached image will be skipped (set a key to generate fresh art)."
		)

	# Infrastructure setup: these errors are worth surfacing (exit 1).
	minio_client = Minio(
		settings.minio_endpoint,
		access_key=settings.minio_access_key,
		secret_key=settings.minio_secret_key,
		secure=settings.minio_secure,
	)
	ensure_public_bucket(minio_client, settings.bucket_public)
	gen_client = genai.Client(api_key=settings.image_api_key) if settings.image_api_key else None
	targets = fetch_scene_targets(settings) + fetch_character_targets(settings)

	if not targets:
		log.warning("No media_assets rows with an object_key found — nothing to seed.")
		return 0

	log.info(
		"Seeding %d image(s) into bucket '%s' (model=%s, force=%s).",
		len(targets),
		settings.bucket_public,
		settings.image_api_model,
		settings.force,
	)

	uploaded = skipped = failed = restored = generated = 0
	for target in targets:
		object_key = target.object_key
		label = target.label
		try:
			if not settings.force and object_exists(minio_client, settings.bucket_public, object_key):
				log.info("skip (exists): %s", label)
				skipped += 1
				continue

			# Prefer a locally cached image (free, deterministic) over an API call.
			# FORCE_REGENERATE_MEDIA ignores the cache on read so `make regen-media` is a true regen.
			data = None if settings.force else _read_cache(settings.backup_dir, object_key)
			from_cache = data is not None
			if from_cache:
				log.info("restored from cache: %s", label)
			elif gen_client is None:
				log.warning("skip (no API key, not in cache): %s", label)
				skipped += 1
				continue
			else:
				data = generate_image(gen_client, settings.image_api_model, target)
				_write_cache(settings.backup_dir, object_key, data)
				log.info("generated + cached: %s", label)

			minio_client.put_object(
				settings.bucket_public, object_key, io.BytesIO(data), length=len(data), content_type="image/png"
			)
			update_size_bytes(settings, target.id, len(data))
			log.info("uploaded: %s (%d bytes)", label, len(data))
			uploaded += 1
			# Counted post-upload: a failed put_object must not inflate restored and
			# drive generated below zero.
			if from_cache:
				restored += 1
			else:
				generated += 1
		except Exception as exc:  # per-scene failure must not abort the rest
			log.error("failed: %s -> %s", label, exc)
			failed += 1

	log.info(
		"Done: %d uploaded (%d restored from cache, %d generated), %d skipped, %d failed.",
		uploaded,
		restored,
		generated,
		skipped,
		failed,
	)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except (psycopg2.OperationalError, S3Error) as exc:
		log.error("Infrastructure error (is postgres/MinIO up?): %s", exc)
		raise SystemExit(1)
