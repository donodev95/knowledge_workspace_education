from datetime import datetime
from typing import Any, Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.app.models import DocumentType, DocumentStatus, ItemType, LinkStatus


class DocumentUploadInput(BaseModel):
    """Metadata accompanying a multipart source-document upload."""

    paper_id: UUID
    document_type: DocumentType
    assessment_number: int | None = Field(default=None, ge=1)
    replaces_document_id: UUID | None = None
    embed: bool = True

    @model_validator(mode='after')
    def validate_assessment_number(self) -> Self:
        if self.document_type == DocumentType.COMPONENT_OVERVIEW:
            if self.assessment_number is not None:
                raise ValueError('Component overviews cannot have an assessment number')
        elif self.assessment_number is None:
            raise ValueError('Assessment briefs and rubrics require an assessment number')
        return self


class SourceDocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    paper_id: UUID
    document_type: DocumentType
    assessment_number: int | None
    replaces_document_id: UUID | None
    original_filename: str
    display_name: str
    mime_type: str
    file_size: int
    content_hash: str
    status: DocumentStatus
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SourceUploadResponse(BaseModel):
    source_document: SourceDocumentPublic
    items_created: int
    embedding_error: str | None = None


class SourceItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_document_id: UUID
    parent_item_id: UUID | None
    item_type: ItemType
    label: str | None
    chunk_index: int
    content: str
    page_number: int | None
    section_title: str | None
    embedding_model: str | None
    metadata_json: dict[str, Any]


class SourceItemLinkCreate(BaseModel):
    """Select an assessment brief to prepare coverage inputs."""

    document_id: UUID


class CoverageInputsPublic(BaseModel):
    paper_id: UUID
    assessment_document_id: UUID
    overview_document_id: UUID
    learning_outcomes: list[SourceItemPublic]
    assessment_requirements: list[SourceItemPublic]


class SourceItemLinkFields(BaseModel):
    from_item_id: UUID
    to_item_id: UUID
    link_type: str = Field(min_length=1, max_length=100)
    status: LinkStatus = LinkStatus.PROPOSED
    rationale: str | None = None


class SourceItemLinkUpdate(BaseModel):
    status: LinkStatus
    rationale: str | None = None


class SourceItemLinkPublic(SourceItemLinkFields):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
