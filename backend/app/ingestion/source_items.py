"""Persist contextual document chunks without separate semantic child items."""
from uuid import uuid4

from backend.app.ingestion.normalization import normalize_text
from backend.app.ingestion.chunking import get_page_number, get_section_title, hash_text
from backend.app.models import ItemType, SourceItem


def convert_to_source_items(document, raw_chunks, chunker, encoding, source_document_id, document_type, classifications=None):
    """Create one source item per context chunk, retaining source provenance."""
    result = []
    if classifications is not None and len(classifications) != len(raw_chunks):
        raise ValueError('Every chunk must have one classification')
    for index, chunk in enumerate(raw_chunks):
        content = chunker.contextualize(chunk)
        normalized = normalize_text(content)
        result.append(SourceItem(
            id=uuid4(), source_document_id=source_document_id,
            item_type=ItemType.CONTEXT, label=classifications[index].choice if classifications is not None else None,
            content=content, normalized_content=normalized,
            content_hash=hash_text(normalized), chunk_index=len(result),
            page_number=get_page_number(chunk),
            section_title=(get_section_title(chunk) or '')[:500] or None,
            token_count=len(encoding.encode(normalized)),
            metadata_json={**chunk.meta.model_dump(mode='json', by_alias=True, serialize_as_any=True),
                           **({'classification': classifications[index].model_dump()} if classifications is not None else {})},
        ))
    return result
