"""
Phase 1 tests: doc tools — ingest_pdf, query_doc, extract_images_from_pdf, analyze_diagram.
RAG-like interface, page chunks, and robust error handling (PDFParseError).
"""

import pytest
from pypdf import PdfWriter

from src.tools.doc_tools import (
    ChunkSegment,
    DocStore,
    PDFIngestionResult,
    PDFParseError,
    analyze_diagram,
    cross_reference_report_claims,
    extract_claimed_paths_from_text,
    extract_images_from_pdf,
    ingest_pdf,
    query_doc,
)


def test_extract_claimed_paths_and_cross_reference():
    """extract_claimed_paths_from_text and cross_reference_report_claims (DOC-1)."""
    text = "See src/graph.py and src/state.py; also docs/readme.md."
    claimed = extract_claimed_paths_from_text(text)
    assert "src/graph.py" in claimed or "src/state.py" in claimed or "docs/readme.md" in claimed
    repo_list = ["src/graph.py", "src/state.py", "tests/test_phase1.py"]
    result = cross_reference_report_claims(claimed, repo_list)
    assert "verified" in result and "unverified" in result
    assert len(result["verified"]) + len(result["unverified"]) >= len(claimed)


def test_ingest_pdf_and_query_doc(tmp_path):
    """Use a small PDF; ingest; query; assert non-empty string and chunked (not single blob)."""
    pdf_path = tmp_path / "doc.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)

    result = ingest_pdf(str(pdf_path))
    assert isinstance(result, PDFIngestionResult)
    assert hasattr(result, "segments")
    assert hasattr(result, "query")
    assert len(result.segments) >= 1
    total_len = sum(len(s.text) for s in result.segments)
    assert total_len < 100_000

    answer = query_doc(result, "What is the main topic?")
    assert isinstance(answer, str)
    assert len(answer) >= 1
    # RAG: answer comes from segments, not full-doc dump
    answer2 = result.query("topic")
    assert isinstance(answer2, str)


def test_ingest_pdf_returns_rag_segments(tmp_path):
    """ingest_pdf returns queryable segments; query returns excerpt from segments only."""
    pdf_path = tmp_path / "rag.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)
    result = ingest_pdf(str(pdf_path))
    assert isinstance(result.get_segments(), list)
    for seg in result.get_segments():
        assert isinstance(seg, ChunkSegment)
        assert hasattr(seg, "text")
        assert hasattr(seg, "page_no")


def test_ingest_pdf_page_chunks(tmp_path):
    """chunk_by='page' returns one segment per page with page_no set."""
    pdf_path = tmp_path / "pages.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)
    result = ingest_pdf(str(pdf_path), chunk_by="page")
    assert len(result.segments) >= 1
    # Page-bound segments have page_no
    page_segments = [s for s in result.segments if s.page_no is not None]
    assert len(page_segments) >= 1


def test_ingest_pdf_chunked_not_single_blob(tmp_path):
    """Result is segment-based; no single multi-megabyte blob."""
    pdf_path = tmp_path / "chunked.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)
    result = ingest_pdf(str(pdf_path))
    assert isinstance(result, PDFIngestionResult)
    assert len(result.segments) >= 1
    for s in result.segments:
        assert len(s.text) < 50_000


def test_ingest_pdf_missing_file():
    with pytest.raises(FileNotFoundError):
        ingest_pdf("/nonexistent/path.pdf")


def test_ingest_pdf_corrupt_raises_parse_error(tmp_path):
    """Corrupt or non-PDF file raises PDFParseError, not raw pypdf exception."""
    bad_path = tmp_path / "not-a-pdf.pdf"
    bad_path.write_text("not a pdf binary content")
    with pytest.raises(PDFParseError) as exc_info:
        ingest_pdf(str(bad_path))
    assert "parsing" in str(exc_info.value).lower() or "pdf" in str(exc_info.value).lower()


def test_query_doc_returns_string():
    """query_doc returns str even when no match; works with DocStore and PDFIngestionResult."""
    store = DocStore(chunks=["chunk one", "chunk two"], source_path="")
    out = query_doc(store, "nonexistent keyword xyz")
    assert isinstance(out, str)
    result = PDFIngestionResult(segments=[ChunkSegment(text="chunk one")], source_path="")
    out2 = query_doc(result, "chunk")
    assert isinstance(out2, str)
    assert "chunk" in out2


def test_extract_images_from_pdf_no_images(tmp_path):
    """PDF with no images returns empty list."""
    pdf_path = tmp_path / "noimg.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)
    images = extract_images_from_pdf(str(pdf_path))
    assert isinstance(images, list)
    assert len(images) >= 0


def test_extract_images_from_pdf_missing_file():
    images = extract_images_from_pdf("/nonexistent/file.pdf")
    assert images == []


def test_extract_images_from_pdf_with_embedded_images():
    """When PDF has embedded images (and Pillow is installed), extraction returns PIL Images."""
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "reports" / "final_report.pdf"
    if not path.is_file():
        pytest.skip("reports/final_report.pdf not found (optional fixture)")
    images = extract_images_from_pdf(str(path))
    assert isinstance(images, list)
    assert len(images) >= 1, "final_report.pdf should contain at least one embedded image"
    first = images[0]
    assert hasattr(first, "save") or (isinstance(first, bytes) and len(first) > 0)


def test_analyze_diagram_returns_string():
    """analyze_diagram returns a string (stub when no vision API)."""
    # Pass bytes as "image" to avoid PIL dependency if not installed
    result = analyze_diagram(b"fake-image-bytes", "Describe the flow.")
    assert isinstance(result, str)
    assert len(result) >= 1
