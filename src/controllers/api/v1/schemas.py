import uuid
from dataclasses import Field

from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    response_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    data: T
