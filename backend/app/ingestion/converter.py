from io import BytesIO
from pathlib import Path

from docling.datamodel.base_models import (
    DocumentStream,
    InputFormat,
)
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import (
    DocumentConverter,
    MarkdownFormatOption,
    PdfFormatOption,
    WordFormatOption,
)
from docling_core.types.doc.document import DoclingDocument


SUPPORTED_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".txt": {"text/plain"},
}


class PaperValidationError(ValueError):
    """Raised when an upload is unsupported, empty, corrupt, or protected."""


def validate_upload(
    filename: str,
    mime_type: str,
    data: bytes,
    max_size_bytes: int,
) -> str:
    """Validate filename, media type, size, and basic file signature."""

    extension = Path(filename).suffix.lower()
    

    if extension not in SUPPORTED_MIME_TYPES:
        raise PaperValidationError(
            "Supported file types are PDF, DOCX, and TXT"
        )

    if mime_type.lower() not in SUPPORTED_MIME_TYPES[extension]:
        raise PaperValidationError(
            "File extension and MIME type do not match"
        )

    if not data:
        raise PaperValidationError(
            "Uploaded file is empty"
        )

    if len(data) > max_size_bytes:
        raise PaperValidationError(
            "Uploaded file exceeds the configured size limit"
        )

    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise PaperValidationError(
            "Invalid PDF signature"
        )

    if extension == ".docx" and not data.startswith(b"PK"):
        raise PaperValidationError(
            "Invalid DOCX signature"
        )

    if extension == ".txt" and b"\x00" in data:
        raise PaperValidationError(
            "TXT uploads cannot contain null bytes"
        )

    return extension


def _extract_pdf_docx(
    converter: DocumentConverter,
    filename: str,
    data: bytes,
) -> DoclingDocument:
    source = DocumentStream(
        name=filename,
        stream=BytesIO(data),
    )

    result = converter.convert(source)

    return result.document


def _extract_txt(
    converter: DocumentConverter,
    filename: str,
    data: bytes,
) -> DoclingDocument:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PaperValidationError(
            "TXT uploads must use UTF-8 encoding"
        ) from exc

    if not text.strip():
        raise PaperValidationError(
            "TXT does not contain text"
        )

    source = DocumentStream(
        name=f"{Path(filename).stem}.md",
        stream=BytesIO(text.encode("utf-8")),
    )

    result = converter.convert(source)

    return result.document


def convert_document(
    extension: str,
    filename: str,
    data: bytes,
    enable_ocr: bool = True,
) -> DoclingDocument:
    """Convert validated upload bytes into a DoclingDocument."""

    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = True
    pipeline_options.do_ocr = enable_ocr
    pipeline_options.do_table_structure = True

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            ),
            InputFormat.DOCX: WordFormatOption(),
            InputFormat.MD: MarkdownFormatOption(),
        }
    )

    if extension in {".pdf", ".docx"}:
        return _extract_pdf_docx(
            converter,
            filename,
            data,
        )

    if extension == ".txt":
        return _extract_txt(
            converter,
            filename,
            data,
        )

    raise PaperValidationError(
        "Unsupported file type"
    )