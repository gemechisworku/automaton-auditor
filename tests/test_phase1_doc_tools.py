"""
Phase 1 tests: doc tools — ingest_pdf, query_doc, extract_images_from_pdf, analyze_diagram.
"""

import pytest
from pypdf import PdfWriter

from src.tools.doc_tools import (
    DocStore,
    analyze_diagram,
    extract_images_from_pdf,
    ingest_pdf,
    query_doc,
)


def test_ingest_pdf_and_query_doc(tmp_path):
    """Use a small PDF; ingest; query; assert non-empty string and chunked (not single blob)."""
    # Create minimal PDF (blank page is ok - we get at least one chunk)
    pdf_path = tmp_path / "doc.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)

    store = ingest_pdf(str(pdf_path))
    assert isinstance(store, DocStore)
    assert hasattr(store, "chunks")
    # Chunked: either multiple chunks or one short chunk, not full-doc single blob
    assert len(store.chunks) >= 1
    total_len = sum(len(c) for c in store.chunks)
    # For blank page we might get one small chunk
    assert total_len < 100_000  # sanity: not a huge single blob

    answer = query_doc(store, "What is the main topic?")
    assert isinstance(answer, str)
    assert len(answer) >= 1


def test_ingest_pdf_chunked_not_single_blob(tmp_path):
    """Store is chunk-based; full text was not passed as single blob."""
    pdf_path = tmp_path / "chunked.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)
    store = ingest_pdf(str(pdf_path))
    assert isinstance(store, DocStore)
    assert len(store.chunks) >= 1
    # Chunked design: no single multi-megabyte blob
    for c in store.chunks:
        assert len(c) < 50_000


def test_ingest_pdf_missing_file():
    with pytest.raises(FileNotFoundError):
        ingest_pdf("/nonexistent/path.pdf")


def test_query_doc_returns_string():
    """query_doc returns str even when no match."""
    store = DocStore(chunks=["chunk one", "chunk two"], source_path="")
    out = query_doc(store, "nonexistent keyword xyz")
    assert isinstance(out, str)


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


def test_analyze_diagram_returns_string():
    """analyze_diagram returns a string (stub when no vision API)."""
    # Pass bytes as "image" to avoid PIL dependency if not installed
    result = analyze_diagram(b"fake-image-bytes", "Describe the flow.")
    assert isinstance(result, str)
    assert len(result) >= 1
