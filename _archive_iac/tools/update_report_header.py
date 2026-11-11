from pathlib import Path

import pymupdf as fitz


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Deliverable1_Report.pdf"
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT = OUTPUT_DIR / "Deliverable1_Report.pdf"


def insert_centered(page: fitz.Page, text: str, y: float, font: str, size: float) -> None:
    width = fitz.get_text_length(text, fontname=font, fontsize=size)
    if width > page.rect.width - 80:
        raise ValueError(f"Text is too wide for the page: {text}")
    x = (page.rect.width - width) / 2
    page.insert_text((x, y), text, fontname=font, fontsize=size, color=(0, 0, 0))


def replace_reference_numbers(
    page: fitz.Page, replacements: list[tuple[str, str]]
) -> None:
    """Replace citation labels while removing the old labels from the text layer."""
    insertions: list[tuple[fitz.Rect, str, float]] = []
    for old, new in replacements:
        matches = page.search_for(old)
        if not matches:
            raise ValueError(f"Reference label not found: {old}")
        for rect in matches:
            font_size = 5.76 if rect.y0 > 500 else 7.488
            redaction = fitz.Rect(rect.x0, rect.y0 - 0.2, rect.x1, rect.y1 + 0.2)
            page.add_redact_annot(redaction, fill=(1, 1, 1))
            insertions.append((rect, new, font_size))

    page.apply_redactions()
    for rect, new, font_size in insertions:
        origin = fitz.Point(rect.x0, rect.y1 - 1.35)
        natural_width = fitz.get_text_length(
            new, fontname="Times-Roman", fontsize=font_size
        )
        horizontal_scale = rect.width / natural_width
        page.insert_text(
            origin,
            new,
            fontname="Times-Roman",
            fontsize=font_size,
            color=(0, 0, 0),
            morph=(origin, fitz.Matrix(horizontal_scale, 1)),
        )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source = fitz.open(SOURCE)
    working = fitz.open(SOURCE)
    first_page = working[0]

    # Reference [9] was removed. Renumber the later sources and every affected
    # in-text citation before rebuilding the pages.
    replace_reference_numbers(
        working[0],
        [("[1, 12]", "[1, 11]"), ("[2, 10]", "[2, 9]")],
    )
    replace_reference_numbers(
        working[1],
        [
            ("[1, 12]", "[1, 11]"),
            ("[2, 10]", "[2, 9]"),
            ("[11]", "[10]"),
            ("[10]", "[9]"),
            ("[12]", "[11]"),
        ],
    )

    # Remove the original title and placeholder identity block so those strings
    # are absent from both the visible page and its extractable text layer.
    first_page.add_redact_annot(fitz.Rect(45, 48, 550, 137), fill=(1, 1, 1))
    first_page.apply_redactions()

    insert_centered(
        first_page,
        "TFGUARD: A Machine Learning-Assisted Framework for",
        68,
        "Times-Bold",
        14.5,
    )
    insert_centered(
        first_page,
        "Security Verification of Infrastructure-as-Code",
        84,
        "Times-Bold",
        14.5,
    )
    insert_centered(
        first_page,
        "Thornkasidej Fuangfoo (6622771234), Varit Mesri (6622771317)",
        101,
        "Times-Roman",
        9.5,
    )
    insert_centered(
        first_page,
        "Sirindhorn International Institute of Technology (SIIT), Thammasat University",
        113,
        "Times-Italic",
        9,
    )
    insert_centered(
        first_page,
        "Adviser: Somchart Fugkeaw",
        125,
        "Times-Italic",
        9,
    )

    # Contribution 1 is orphaned across the original page break. Remove the
    # section from page 1; it is copied intact to the top of the rebuilt page 2.
    first_page.add_redact_annot(fitz.Rect(45, 747, 550, 806), fill=(1, 1, 1))
    first_page.apply_redactions()

    output = fitz.open()
    output.insert_pdf(working, from_page=0, to_page=0)
    second_page = output.new_page(width=595, height=842)

    # Preserve the original vector text and typography while producing a clean
    # section break: section 3 first, followed by the original page-2 content.
    second_page.show_pdf_page(
        fitz.Rect(0, 40, 595, 99),
        source,
        0,
        clip=fitz.Rect(0, 747, 595, 806),
    )
    second_page.show_pdf_page(
        fitz.Rect(0, 99, 595, 598),
        working,
        1,
        clip=fitz.Rect(0, 50, 595, 549),
    )
    # Skip the two lines belonging to removed reference [9], then pull the
    # remaining bibliography upward to close the gap.
    second_page.show_pdf_page(
        fitz.Rect(0, 598, 595, 653.45),
        working,
        1,
        clip=fitz.Rect(0, 564.55, 595, 620),
    )

    # Add unobtrusive page numbers in the existing bottom margin.
    for number, page in enumerate(output, start=1):
        insert_centered(page, str(number), 824, "Helvetica", 8)

    metadata = source.metadata or {}
    metadata.update(
        {
            "title": "TFGUARD: A Machine Learning-Assisted Framework for Security Verification of Infrastructure-as-Code",
            "author": "Thornkasidej Fuangfoo; Varit Mesri",
            "subject": "SIIT, Thammasat University - Infrastructure-as-Code security verification project report",
            "keywords": "Terraform, Infrastructure-as-Code, security, XGBoost, SHAP",
        }
    )
    output.set_metadata(metadata)
    if OUTPUT.exists():
        OUTPUT.unlink()
    output.save(OUTPUT, garbage=4, deflate=True)
    output.close()
    working.close()
    source.close()
    print(OUTPUT)


if __name__ == "__main__":
    main()
