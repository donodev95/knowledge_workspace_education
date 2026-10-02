from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaperCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)

    @field_validator('code', 'title', mode='before')
    @classmethod
    def strip_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('code')
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class PaperPublic(PaperCreate):
    model_config = ConfigDict(from_attributes=True)
    owner_id: UUID | None
    id: UUID
    created_at: datetime
    updated_at: datetime
