"""Deterministic, provenance-preserving extraction; semantic labels need review."""
from collections import Counter
import re
from uuid import uuid4

from backend.app.ingestion.normalization import normalize_text
from backend.app.ingestion.chunking import get_page_number, get_section_title, hash_text
from backend.app.models import DocumentType, ItemType, SourceItem

_OUTCOME = re.compile(r"^(?:[-•]\s*)?(?:LO\s*\d+[:.)]?|[a-z][.)]|\d+[.)])\s+", re.I)
_TASK = re.compile(r"\btask\s*(\d+)\b", re.I)


def extract_source_items(document, raw_chunks, chunker, encoding, source_document_id, document_type):
    """Keep retrieval context and add one child per explicitly structured requirement."""
    result = []
    parents = {}
    counters = Counter()

    def append(content, kind, *, label=None, page=None, section=None, parent=None, metadata=None):
        normalized = normalize_text(content)
        item = SourceItem(
            id=uuid4(), 
            source_document_id=source_document_id,
            parent_item_id=parent, 
            item_type=kind, 
            label=label,
            content=content, 
            normalized_content=normalized, 
            content_hash=hash_text(normalized),
            chunk_index=len(result), 
            page_number=page, 
            section_title=(section or '')[:500] or None,
            token_count=len(encoding.encode(normalized)), 
            metadata_json=metadata or {},
        )
        result.append(item)
        return item

    for chunk in raw_chunks:
        parent = append(chunker.contextualize(chunk), 
                        ItemType.CONTEXT,
                        page=get_page_number(chunk), 
                        section=get_section_title(chunk),
                        metadata=chunk.meta.model_dump(mode='json', by_alias=True, serialize_as_any=True)
                        )
        for item in getattr(chunk.meta, 'doc_items', []):
            parents.setdefault(item.self_ref, parent.id)

    section = ''
    task = None
    mode = None
    seen = set()
    for item, _ in document.iterate_items():
        ref = item.self_ref
        if ref in seen:
            continue
        seen.add(ref)
        text = getattr(item, 'text', '')
        label = str(item.label)
        if label in ('section_header', 'title'):
            section = normalize_text(text)
            normalized_heading = ' '.join(section.casefold().split()).rstrip(':')
            task_match = _TASK.search(section)
            if normalized_heading == 'learning outcomes' and document_type == DocumentType.COMPONENT_OVERVIEW:
                mode, task = ItemType.LEARNING_OUTCOME, None
            elif document_type != DocumentType.COMPONENT_OVERVIEW and any(word in normalized_heading for word in ('rubric', 'criteria')):
                mode, task = ItemType.RUBRIC_CRITERION, None
            elif document_type == DocumentType.ASSESSMENT_BRIEF and task_match:
                mode, task = ItemType.ASSESSMENT_REQUIREMENT, task_match.group(1)
            elif mode == ItemType.ASSESSMENT_REQUIREMENT and re.match(r'^\d+[.)]\s', section):
                pass  # Numbered task subsections, such as "2. Data Cleaning".
            elif document_type == DocumentType.RUBRIC:
                mode, task = ItemType.RUBRIC_CRITERION, None
            else:
                mode, task = None, None
            continue
        if label in ('page_header', 'page_footer'):
            continue
        active_mode = mode or (ItemType.RUBRIC_CRITERION if document_type == DocumentType.RUBRIC else None)
        candidates = []
        if active_mode == ItemType.RUBRIC_CRITERION and label == 'table':
            rows = {}
            for cell in item.data.table_cells:
                if not cell.column_header:
                    rows.setdefault(cell.start_row_offset_idx, []).append(cell)
            for row_index, cells in sorted(rows.items()):
                content = ' | '.join(cell.text for cell in sorted(cells, key=lambda c: c.start_col_offset_idx) if cell.text.strip())
                if content:
                    candidates.append((content, {'table_row': row_index}))
        elif active_mode and text.strip():
            # Introductory paragraphs stay in context, not in the outcome list.
            if label == 'list_item' or (active_mode == ItemType.LEARNING_OUTCOME and _OUTCOME.match(normalize_text(text))):
                candidates.append((text, {}))
        if not active_mode or not candidates:
            continue
        for content, extra in candidates:
            prefix = {
                ItemType.LEARNING_OUTCOME: "lo",
                ItemType.ASSESSMENT_REQUIREMENT: f"task_{task}_requirement",
                ItemType.RUBRIC_CRITERION: "criterion",
            }[active_mode]

            counters[prefix] += 1

            append(content, 
                   active_mode, 
                   label=f'{prefix}_{counters[prefix]}',
                   page=min((p.page_no for p in item.prov), default=None), 
                   section=section,
                   parent=parents.get(ref), 
                   metadata={
                       'source_ref': ref,
                       'provenance': [p.model_dump(mode='json') for p in item.prov],
                       'extraction_method': 'structured_source_item', 'review_required': True,
                       **extra,
                   })
    return result
