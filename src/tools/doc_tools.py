"""
PDF and vision forensic tools. Chunked ingestion (RAG-lite); image extraction; diagram analysis.
Explicit RAG-like interface: chunked, queryable segments (page/semantic) + query function.
API Contracts §5.2; SRS FR-8, FR-9.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pypdf import PdfReader


# Chunk size in characters for RAG-lite (avoid dumping full doc into context)
_CHUNK_SIZE = 1500
_CHUNK_OVERLAP = 100


class PDFParseError(Exception):
    """Raised when PDF parsing fails (corrupt file, unsupported format, etc.)."""

    def __init__(self, message: str, path: str = "", cause: Exception | None = None):
        self.path = path
        self.cause = cause
        super().__init__(message or f"PDF parsing failed: {path}")


@dataclass
class ChunkSegment:
    """A single queryable segment (page-bound or character-bound) for RAG retrieval."""

    text: str
    page_no: int | None = None  # 1-based; None for merged char chunks


@dataclass
class PDFIngestionResult:
    """
    RAG-like result of PDF ingestion: chunked, queryable segments plus a query function.
    Does not dump full document text; retrieval is via query(question).
    """

    segments: list[ChunkSegment]
    source_path: str

    def query(self, question: str, top_k: int = 5) -> str:
        """Return relevant excerpts for the question (chunked retrieval)."""
        texts = [s.text for s in self.segments]
        relevant = _search_chunks(texts, question, top_k)
        if not relevant:
            return "No relevant excerpts found."
        return "\n\n---\n\n".join(relevant)

    def get_segments(self) -> list[ChunkSegment]:
        """Return the chunked segments (e.g. for inspection or custom retrieval)."""
        return list(self.segments)


def _search_chunks(chunks: list[str], question: str, top_k: int = 5) -> list[str]:
    """Return chunks most relevant to question (simple keyword overlap)."""
    q_lower = question.lower()
    q_words = set(w for w in q_lower.split() if len(w) > 2)
    scored = []
    for c in chunks:
        c_lower = c.lower()
        score = sum(1 for w in q_words if w in c_lower)
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k]]


@dataclass
class DocStore:
    """
    Queryable store of chunked PDF text (RAG-lite).
    Implements the same RAG contract as PDFIngestionResult; kept for backward compatibility.
    """

    chunks: list[str]
    source_path: str

    def search_chunks(self, question: str, top_k: int = 5) -> list[str]:
        """Return chunks most relevant to question (simple keyword overlap)."""
        return _search_chunks(self.chunks, question, top_k)

    def query(self, question: str, top_k: int = 5) -> str:
        """RAG-like query: return relevant excerpts for the question."""
        relevant = self.search_chunks(question, top_k)
        if not relevant:
            return "No relevant excerpts found."
        return "\n\n---\n\n".join(relevant)


def ingest_pdf(
    pdf_path: str,
    chunk_by: Literal["char", "page"] = "char",
) -> PDFIngestionResult:
    """
    Ingest PDF into chunked, queryable segments (RAG-like; no full-text dump). SRS FR-8.
    - chunk_by="char": merge pages then split by character count (default).
    - chunk_by="page": one segment per page (page-bound chunks).
    Raises FileNotFoundError if file missing; PDFParseError on parse/corrupt PDF.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        raise PDFParseError(
            f"PDF parsing failed: {pdf_path}. {type(e).__name__}: {e}",
            path=pdf_path,
            cause=e,
        ) from e

    page_texts: list[tuple[int, str]] = []  # 1-based page_no, text
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text()
            page_texts.append((i + 1, (t or "").strip() or "(no text)"))
        except Exception as e:
            raise PDFParseError(
                f"Failed to extract text from page {i + 1}: {pdf_path}. {type(e).__name__}: {e}",
                path=pdf_path,
                cause=e,
            ) from e

    if chunk_by == "page":
        segments = [ChunkSegment(text=t, page_no=p) for p, t in page_texts]
        if not segments:
            segments = [ChunkSegment(text="(no text extracted)", page_no=None)]
    else:
        full = "\n\n".join(t for _, t in page_texts)
        chunks = _split_into_chunks(full, _CHUNK_SIZE, _CHUNK_OVERLAP)
        segments = [ChunkSegment(text=c, page_no=None) for c in chunks]
        if not segments:
            segments = [ChunkSegment(text="(no text)", page_no=None)]

    return PDFIngestionResult(segments=segments, source_path=pdf_path)


def _split_into_chunks(text: str, size: int, overlap: int) -> list[str]:
    out = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        if chunk.strip():
            out.append(chunk.strip())
        start = end - overlap
    return out if out else [text[:size].strip() or "(no text)"]


def query_doc(store: DocStore | PDFIngestionResult, question: str) -> str:
    """Query the store (RAG retrieval over chunked segments). Accepts DocStore or PDFIngestionResult."""
    if hasattr(store, "query") and callable(getattr(store, "query")):
        return store.query(question)
    relevant = store.search_chunks(question, top_k=5)
    if not relevant:
        return "No relevant excerpts found."
    return "\n\n---\n\n".join(relevant)


def extract_images_from_pdf(pdf_path: str) -> list[Any]:
    """
    Extract images from PDF for VisionInspector. Returns list of image-like objects
    (PIL Image or bytes). Uses pypdf page.images where available.
    """
    path = Path(pdf_path)
    if not path.is_file():
        return []

    images: list[Any] = []
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            img_attr = getattr(page, "images", None)
            if img_attr is None:
                continue
            # pypdf 4: page.images is dict-like; iterate keys for error handling
            for name in (img_attr.keys() if hasattr(img_attr, "keys") else []):
                try:
                    img_obj = img_attr[name]
                    if hasattr(img_obj, "image"):
                        images.append(img_obj.image)
                    elif hasattr(img_obj, "data"):
                        images.append(img_obj.data)
                except Exception:
                    continue
    except Exception:
        pass
    return images


def analyze_diagram(image: Any, question: str) -> str:
    """
    Use vision-capable LLM to answer flow/structure questions about the image.
    Optional at runtime; if no vision API key or LLM unavailable, returns a stub message.
    Requires langchain-openai (or equivalent) for real vision; otherwise returns stub.
    """
    try:
        from langchain_core.messages import HumanMessage

        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            return "[Vision analysis skipped: install langchain-openai and set OPENAI_API_KEY for diagram analysis.]"

        model = ChatOpenAI(model="gpt-4o", temperature=0)
        # Support PIL Image or bytes
        if hasattr(image, "save"):
            import base64
            import io

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            img_b64 = base64.standard_b64encode(buf.getvalue()).decode()
            msg = HumanMessage(
                content=[
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ]
            )
        else:
            msg = HumanMessage(content=[{"type": "text", "text": question}])
        response = model.invoke([msg])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        return f"[Vision analysis skipped or failed: {e}. Set OPENAI_API_KEY for GPT-4o vision.]"
