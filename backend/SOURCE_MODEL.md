# Academic papers and source ingestion

`Paper` is an academic identity (`code`, `title`). Each upload creates a separate
`SourceDocument`, even when its bytes repeat an earlier upload. Its file hash is
SHA-256; a replacement points to an existing upload of the same paper, document
type, and assessment number.

## API flow

1. `POST /api/v1/papers` with JSON `{"code":"DMV302","title":"Data Mining & Visualizations"}`.
2. `POST /api/v1/documents/upload` using multipart fields:
   - `file`
   - `paper_id` from step 1
   - `document_type`: `component_overview`, `assessment_brief`, or `rubric`
   - `assessment_number`: required for briefs/rubrics; omit for overviews
   - `replaces_document_id`: optional previous upload ID
   - `embed`: defaults to `true`; use `false` for extraction only
3. Read items using `GET /api/v1/documents/{id}/items`.
4. Retry or request embeddings using `POST /api/v1/documents/{id}/embed`.

The upload response contains `source_document`, `items_created`, and
`embedding_error`. It replaces the old `paper`/`assessment` upload response.
The upload field `file_type` is replaced by `document_type`.
Deleting `/documents/{id}` removes that upload, its items, and its links; it does
not delete the academic paper.

## Items and links

Context chunks and individual outcomes, task list requirements, and rubric list
items/table rows share `source_items`. Outcome labels are `LO1`, `LO2`, etc.; the
introductory sentence remains context. Task requirements use `Task 1 R1`, etc.;
rubric criteria use `RC1`, etc. Extraction follows explicit document structure,
not semantic inference. Unstructured paragraphs remain context. Extracted semantic
items have `review_required=true`; nested lists and complex rubric tables should
be reviewed. Original source references and page provenance are retained.

Each item has a unique position within its upload. Repeated text is allowed.
Semantic items point to their context item when available. GIN indexes JSON
metadata; HNSW indexes the nullable 1024-dimensional embedding using cosine distance.

Generate coverage proposals using `POST /api/v1/source-item-links` as described below.
Review links using `PATCH /api/v1/source-item-links/{id}`.

## Embedding lifecycle

Extraction is committed before calling the embedding provider. Without embedding,
the document is `extracted`. On success it is `completed`, and every embedded item
records the provider's model name. On embedding failure it becomes
`embedding_failed`, but its text and items remain available. Retrying targets only
items without embeddings. Invalid dimensions and non-finite vectors are rejected.

## Migration

Run `.venv/bin/alembic upgrade head` before starting the updated application.
The migration copies existing uploads, chunks, embeddings, and jobs into the new
schema. Old tables are retained as `legacy_*` archives and excluded from future
Alembic autogeneration. Existing uploads get explicit `LEGACY-*` paper codes because
the previous schema did not identify academic papers or assessment-to-paper mappings.
Their titles come from the old display names and need curation. Assessment numbers
remain unknown (`NULL`) for migrated records; new uploads require them.

Legacy item metadata records the old ID/table and flags it for review. Existing
embedding model names were never stored, so migrated embeddings retain `NULL`
model names and an `embedding_model_unknown` flag rather than inventing provenance.
Legacy assessment chunks remain context: individual requirements need re-extraction
from the original upload. Existing introductory outcome text is preserved as context.

This migration has no automatic downgrade: reverting could discard new uploads or
reviewed links. Restore a pre-migration database backup to revert the application.

## User ownership and JWT authentication

All routes, including `/`, documentation, and OpenAPI, require
`Authorization: Bearer <access_token>` except `/api/v1/auth/register` and
`/api/v1/auth/login`. Login returns the token. A browser visit to documentation
without an Authorization header now returns 401; send the header when fetching
both the documentation page and its OpenAPI schema.

New papers and ingestion jobs get `owner_id` from the authenticated user, never
from request input. Threads already have `owner_id`. Paper codes are unique per
owner. Document, item, and link access follows the owning paper; foreign resources
return 404. Inactive or deleted accounts cannot use previously issued tokens.

Migration `b28d75e64f39` leaves existing paper/job ownership NULL because historical
ownership was not recorded. Those papers are hidden from all users. Assign each
legacy paper to its verified user before using it, then update its ingestion jobs
through `source_document_id -> source_documents.paper_id`. Nullable ownership is
reserved for these historical records; normal application creation requires an owner.

## Coverage analysis MVP

`POST /api/v1/source-item-links` now runs coverage analysis (it replaces the previous
manual-pair and document-only request shapes):

```json
{
  "paper_id": "<paper UUID>",
  "assessment_number": 1,
  "include_partial": true
}
```

Optional `overview_document_id` and `assessment_document_id` select exact versions.
Otherwise a current document is one not replaced by another document of the same
paper/type/assessment. Multiple current documents produce 409. A pending/failed
replacement is not silently bypassed in favor of its old version. Both selected
documents must have completed extraction, and both semantic item lists must be
nonempty. Embedding failure does not prevent coverage analysis.

Configure `LLM_PROVIDER=ollama`, `LLM_MODEL`, and optionally `LLM_BASE_URL` (the native
Ollama server, normally `http://localhost:11434`, not its `/v1` endpoint).
Every eligible requirement is compared with every eligible outcome. Calls reuse one
Ollama client, with thinking disabled and compact source fields. Source content is
data, never instructions; explicit LO references alone do not establish coverage.

The response includes item counts, every pair's judgment, original source passages,
IDs, labels, page/section details, parent_item_id, proposals, unresolved pairs,
outcomes awaiting review, and outcomes with no suggested match. Parent IDs retain
the ingestion hierarchy (currently often a context chunk, not a dedicated task).
This does not repair missed extraction or establish full coverage from incomplete
source inputs.

Proposals use `assessment_requirement -> learning_outcome` with
`link_type=addresses_outcome`. Full and partial matches are proposed by default;
`include_partial=false` excludes partial matches from proposal creation. Unique-key
conflicts do nothing: reruns do not duplicate or overwrite proposals or human review
decisions. Stored link rationale and current pair rationale are returned separately
so disagreements remain visible. Failed judgments are returned to the caller, not
persisted as links or converted to negative matches.

`PATCH /source-item-links/{id}` accepts status and rationale, validates ownership,
and returns confirmed coverage for that exact brief/overview pair. Confirmed coverage
is the fraction of outcomes having at least one confirmed `addresses_outcome` link.
Proposals and rejected links never count. Confirming a partial proposal counts its
outcome under this binary metric; reviewers should confirm only evidence they accept
for coverage. This is not a graded measure of every subcomponent of an outcome.


### MVP coverage flow

Coverage analysis uses the restored small-batch algorithm: up to four requirements
per call, compared with all learning outcomes. `batch_size` accepts 1–5. Task labels
influence ordering, but do not force singleton calls or oversized task batches.
For 22 eligible requirements, the default produces six calls (4,4,4,4,4,2).

The per-call and overall timeout defaults remain 120 and 600 seconds. Token budget
sets the Ollama context size. Failed calls remain unresolved; positive validated
judgments create proposed links. Existing proposals skip inference unless refreshed,
and confirmed/rejected links are never overwritten. Ownership checks remain enabled.

The grouped `outcome_reviews` response is retained. No cache, file exports, or
batch-history writes are performed. No database migration is required.
