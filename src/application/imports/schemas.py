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
