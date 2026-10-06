"""Inspect the Docling items extracted from a text chunk."""
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter


def print_docling_items(text: str) -> None:
    """Parse text as Markdown and print each item's structured output."""
    if not text.strip():
        raise ValueError("Provide a non-empty text chunk")
    document = DocumentConverter(allowed_formats=[InputFormat.MD]).convert_string(
        text, format=InputFormat.MD, name="text_chunk",
    ).document
    for index, (item, level) in enumerate(document.iterate_items(), start=1):
        print(f"\nItem {index} · level {level} · {item.label}")
        print(item.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    print_docling_items("""
Component Description and Aims
This component aims to teach students data mining techniques for both structured and unstructured data. Students will be able to analyse moderate-to-large sized datasets, data preparation, handling missing data, modelling, prediction and classification. Students will also be able to communicate complex information in results of data analytics through effective visualization techniques.
""")
