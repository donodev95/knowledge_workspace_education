from pathlib import Path

from docling.document_converter import DocumentConverter
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from docling_core.types.doc.items.text import ListItem, TextItem
import re
from pprint import pprint

def extract_learning_outcomes(doc: DoclingDocument) -> list[dict]:
    outcomes = []
    current = None
    in_section = False
    reached_end = False

    # Matches this document's labels: a), b), c), d), e)
    marker_pattern = re.compile(r"^\s*([a-e])\)\s*", re.IGNORECASE)

    for item, _ in doc.iterate_items():
        pprint(item)
        # if not isinstance(item, TextItem):
        #     continue

        # if item.label in {
        #     DocItemLabel.PAGE_HEADER,
        #     DocItemLabel.PAGE_FOOTER,
        # }:
        #     continue

        # text = item.text.strip()
        # heading = " ".join(text.split()).casefold()

        # if heading == "learning outcomes":
        #     in_section = True
        #     continue

        # if not in_section:
        #     continue

        # if heading == "workload and engagement":
        #     reached_end = True
        #     break

        # # Some conversions store the list marker outside item.text.
        # if isinstance(item, ListItem) and item.marker:
        #     if not marker_pattern.match(text):
        #         text = f"{item.marker} {text}"

        # for line in text.splitlines():
        #     line = line.strip()
        #     if not line:
        #         continue

        #     match = marker_pattern.match(line)

        #     if match:
        #         current = {
        #             "item_type": "learning_outcome",
        #             "label": f"{match.group(1).lower()})",
        #             "text": line[match.end():].strip(),
        #             "source_refs": [],
        #             "page_numbers": [],
        #         }
        #         outcomes.append(current)

        #     elif current is not None:
        #         # Preserve wrapped lines as part of the same outcome.
        #         current["text"] += " " + line

        #     else:
        #         # Skip the introductory sentence before a).
        #         continue

        #     if item.self_ref not in current["source_refs"]:
        #         current["source_refs"].append(item.self_ref)

        #     current["page_numbers"] = sorted(
        #         set(current["page_numbers"])
        #         | {prov.page_no for prov in item.prov}
        #     )

    # # Validation specific to this PDF.
    # if not in_section or not reached_end:
    #     raise ValueError("Could not identify learning-outcome section boundaries.")

    # if [outcome["label"] for outcome in outcomes] != [
    #     "a)", "b)", "c)", "d)", "e)"
    # ]:
    #     raise ValueError("Expected five outcomes labelled a)–e); inspect extraction.")

    # if any(not outcome["text"] for outcome in outcomes):
    #     raise ValueError("An extracted learning outcome is empty.")

    return outcomes

def convert_pdf(file_path: str | Path) -> DoclingDocument:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {path}")

    converter = DocumentConverter()
    result = converter.convert(path)

    return result.document


docling_document = convert_pdf("./data/Component_Overview.pdf")

# Use the extraction function from the previous message.
learning_outcomes = extract_learning_outcomes(docling_document)

for outcome in learning_outcomes:
    print(f"{outcome['label']} {outcome['text']}")
    