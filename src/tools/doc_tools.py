"""
PDF and vision forensic tools. Chunked ingestion (RAG-lite); image extraction; diagram analysis.
API Contracts §5.2; SRS FR-8, FR-9.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader


# Chunk size in characters for RAG-lite (avoid dumping full doc into context)
_CHUNK_SIZE = 1500
_CHUNK_OVERLAP = 100


@dataclass
class DocStore:
    """Queryable store of chunked PDF text (RAG-lite)."""

    chunks: list[str]
    source_path: str

    def search_chunks(self, question: str, top_k: int = 5) -> list[str]:
        """Return chunks most relevant to question (simple keyword overlap)."""
        q_lower = question.lower()
        q_words = set(w for w in q_lower.split() if len(w) > 2)
        scored = []
        for c in self.chunks:
            c_lower = c.lower()
            score = sum(1 for w in q_words if w in c_lower)
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k]]


def ingest_pdf(pdf_path: str) -> DocStore:
    """
    Chunk PDF text; return queryable store. Does not dump full text into a single string (SRS FR-8).
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    reader = PdfReader(pdf_path)
    all_texts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text()
            if t:
                all_texts.append(t)
        except Exception:
            continue

    full = "\n\n".join(all_texts)
    chunks = _split_into_chunks(full, _CHUNK_SIZE, _CHUNK_OVERLAP)
    return DocStore(chunks=chunks, source_path=pdf_path)


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


def query_doc(store: DocStore, question: str) -> str:
    """Query the store; return answer or excerpt (chunked retrieval)."""
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
