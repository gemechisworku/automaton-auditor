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


def extract_claimed_paths_from_text(text: str) -> list[str]:
    """
    Extract file/path-like strings from text (e.g. PDF report content) for cross-reference.
    Returns a list of normalized path-like strings (e.g. src/graph.py, docs/readme.md).
    Includes both path-style (src/foo.py) and bare filenames (state.py) to improve
    verification rate when the report cites files without full path.
    """
    import re
    # Path-style: src/foo.py, docs/readme.md, etc.
    path_pattern = (
        r"\b(?:src|docs|tests|scripts?|config)/[a-zA-Z0-9_./\-]+\.[a-zA-Z0-9]+\b"
        r"|\b[a-zA-Z0-9_]+/[a-zA-Z0-9_./\-]+\b"
    )
    # Bare filenames that look like code/docs (e.g. state.py, README.md)
    bare_pattern = r"\b[a-zA-Z0-9_]+\.(?:py|md|json|txt|yaml|yml|toml)\b"
    found = list(re.findall(path_pattern, text)) + list(re.findall(bare_pattern, text))
    normalized = []
    seen: set[str] = set()
    for p in found:
        p = p.strip().replace("\\", "/")
        if not p or p in seen or len(p) < 2 or len(p) > 200:
            continue
        seen.add(p)
        normalized.append(p)
    return normalized


def cross_reference_report_claims(
    claimed_paths: list[str], repo_file_list: list[str]
) -> dict[str, list[str]]:
    """
    Cross-reference claimed file paths (e.g. from PDF report) with repo file list.
    Returns {"verified": [...], "unverified": [...]}.
    Uses exact match, then suffix match (e.g. graph.py vs src/graph.py), and
    case-normalized comparison so paths that exist are not wrongly marked unverified.
    """
    # Normalize: forward slashes, strip, and build case-insensitive lookup for matching
    def norm(s: str) -> str:
        return s.replace("\\", "/").strip()

    repo_normalized = [norm(f) for f in repo_file_list if f]
    repo_set = set(repo_normalized)
    # For suffix matching: repo paths as-is; also lowercase set for case-insensitive match
    repo_lower = {r.lower(): r for r in repo_set}

    verified: list[str] = []
    unverified: list[str] = []

    for p in claimed_paths:
        p_norm = norm(p)
        if not p_norm:
            continue
        # 1) Exact match (case-sensitive)
        if p_norm in repo_set:
            verified.append(p_norm)
            continue
        # 2) Exact match (case-insensitive)
        if p_norm.lower() in repo_lower:
            verified.append(p_norm)
            continue
        # 3) Claimed path is suffix of a repo path (e.g. graph.py vs src/graph.py)
        if any(r == p_norm or r.endswith("/" + p_norm) for r in repo_set):
            verified.append(p_norm)
            continue
        if any(r.lower().endswith("/" + p_norm.lower()) for r in repo_set):
            verified.append(p_norm)
            continue
        # 4) Repo path contains claimed path as segment (e.g. src/graph.py in repo)
        if any(p_norm in r or p_norm.lower() in r.lower() for r in repo_set):
            verified.append(p_norm)
            continue
        unverified.append(p_norm)

    return {"verified": verified, "unverified": unverified}


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
    (PIL Image or bytes). Requires pypdf[image] (Pillow) for extraction.

    Uses pypdf page.images: iterates over each page's images and collects PIL Images
    (or raw bytes if .image is not available). If Pillow is not installed, returns [].

    Limitation (VISION-1): Many PDFs embed diagrams as vector graphics (drawing operations)
    rather than embedded image objects. In those cases page.images may be empty even when
    the PDF contains diagrams. VisionInspector will then report "No images extracted from PDF."
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
            # pypdf 4+: page.images is iterable; each item is ImageFile (.image = PIL, .data = bytes). Requires Pillow.
            for img_obj in img_attr:
                try:
                    if hasattr(img_obj, "image") and img_obj.image is not None:
                        images.append(img_obj.image)
                    elif hasattr(img_obj, "data") and img_obj.data:
                        images.append(img_obj.data)
                except ImportError:
                    raise
                except Exception:
                    continue
    except ImportError as e:
        if "pillow" in str(e).lower() or "pypdf" in str(e).lower() or "image" in str(e).lower():
            pass  # Return [] when pypdf[image] not installed
        else:
            raise
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
