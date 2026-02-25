"""
Generate PDF from the architecture report HTML.
Requires: pip install weasyprint  (or uv add --dev weasyprint)
Output: docs/architecture_report.pdf
If weasyprint is not installed, prints instructions to use browser Print → Save as PDF.
"""

from pathlib import Path


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    html_path = base / "docs" / "architecture_report.html"
    pdf_path = base / "docs" / "architecture_report.pdf"

    if not html_path.is_file():
        print(f"Not found: {html_path}")
        return

    try:
        from weasyprint import HTML  # type: ignore
    except ImportError:
        print("WeasyPrint not installed. To generate PDF from HTML:")
        print("  uv add --dev weasyprint")
        print("  uv run python scripts/generate_report_pdf.py")
        print("Alternatively, open docs/architecture_report.html in a browser and use Print → Save as PDF.")
        return

    print(f"Writing {pdf_path} ...")
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    print(f"Done: {pdf_path}")


if __name__ == "__main__":
    main()
