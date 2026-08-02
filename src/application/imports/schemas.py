from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ImportLorebookResultDTO(BaseModel):
	model_config = ConfigDict(frozen=True)

	characters_created: int
	scenes_created: int
	images_imported: int
	image_failures: list[str]
	character_ids: list[UUID]
	scene_ids: list[UUID]
	skipped_entries: int


class ImportCandidateDTO(BaseModel):
	model_config = ConfigDict(frozen=True)

	key: str
	uid: str | int | None
	name: str
	group: str
	content_preview: str
	content_length: int
	image_count: int


class ImportPreviewDTO(BaseModel):
	model_config = ConfigDict(frozen=True)

	characters: list[ImportCandidateDTO]
	scenes: list[ImportCandidateDTO]
	other_entries: int
	skipped_entries: int
	world_context_preview: str
