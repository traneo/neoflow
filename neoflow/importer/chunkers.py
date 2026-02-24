"""Document-type-aware chunkers for the documentation importer.

To add a new chunker:
1. Subclass ``DocChunker`` and implement ``chunk()``.
2. Register it in ``_CHUNKER_REGISTRY`` with a doc-type key.
3. Map the relevant file extensions to that key in ``_EXTENSION_TO_DOC_TYPE``.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _truncate_chunk(chunk: str, max_bytes: int) -> str:
    encoded = chunk.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return chunk
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _generic_line_chunk(content: str, chunk_size_bytes: int) -> list[str]:
    """Fallback: split on raw lines when a section exceeds the size budget."""
    # Imported lazily to avoid a hard circular dependency at module load time.
    from neoflow.importer.code_indexer import chunk_content  # noqa: PLC0415
    return chunk_content(content, chunk_size_bytes)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class DocChunker(ABC):
    """Abstract base for document-type-aware chunkers."""

    @abstractmethod
    def chunk(self, content: str, chunk_size_bytes: int) -> list[str]:
        """Return a list of chunks, each ≤ *chunk_size_bytes* bytes (UTF-8)."""


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

class MarkdownChunker(DocChunker):
    """Split Markdown at heading boundaries (``#`` through ``######``)."""

    _HEADING = re.compile(r"^#{1,6} ", re.MULTILINE)

    def chunk(self, content: str, chunk_size_bytes: int) -> list[str]:
        splits = [m.start() for m in self._HEADING.finditer(content)]
        if not splits:
            return _generic_line_chunk(content, chunk_size_bytes)

        sections: list[str] = []
        if splits[0] > 0:
            sections.append(content[: splits[0]])
        for i, start in enumerate(splits):
            end = splits[i + 1] if i + 1 < len(splits) else len(content)
            sections.append(content[start:end])

        return self._pack(sections, chunk_size_bytes)

    def _pack(self, sections: list[str], chunk_size_bytes: int) -> list[str]:
        chunks: list[str] = []
        current_parts: list[str] = []
        current_size = 0
        last_heading = ""

        for section in sections:
            section_bytes = len(section.encode("utf-8", errors="replace"))

            if section_bytes > chunk_size_bytes:
                if current_parts:
                    chunks.append("".join(current_parts))
                    current_parts = []
                    current_size = 0
                chunks.extend(_generic_line_chunk(section, chunk_size_bytes))
                continue

            if current_parts and current_size + section_bytes > chunk_size_bytes:
                chunks.append("".join(current_parts))
                # Carry the previous heading as overlap context.
                current_parts = [last_heading] if last_heading else []
                current_size = len(last_heading.encode("utf-8", errors="replace"))

            first_line = section.split("\n", 1)[0]
            if self._HEADING.match(first_line):
                last_heading = first_line + "\n"

            current_parts.append(section)
            current_size += section_bytes

        if current_parts:
            chunks.append("".join(current_parts))

        return [_truncate_chunk(c, chunk_size_bytes) for c in chunks] or [content]


# ---------------------------------------------------------------------------
# reStructuredText
# ---------------------------------------------------------------------------

class RSTChunker(DocChunker):
    """Split reStructuredText at section-title boundaries.

    Recognises both underline-only and overline+underline title styles.
    """

    # Any line consisting entirely of 4+ repeated RST adornment characters.
    _ADORNMENT = re.compile(
        r'^([!"#$%&\'()*+,\-./:;<=>?@\[\\\]^_`{|}~])\1{3,}\s*$'
    )

    def _find_section_starts(self, lines: list[str]) -> list[int]:
        """Return the indices (into *lines*) where each section title begins."""
        starts: list[int] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Overline + underline: adornment / title / adornment
            if (
                self._ADORNMENT.match(line)
                and i + 2 < len(lines)
                and lines[i + 1].strip()
                and self._ADORNMENT.match(lines[i + 2])
            ):
                starts.append(i)
                i += 3
                continue
            # Underline only: non-empty non-adornment line / adornment
            if (
                line.strip()
                and not self._ADORNMENT.match(line)
                and i + 1 < len(lines)
                and self._ADORNMENT.match(lines[i + 1])
            ):
                starts.append(i)
                i += 2
                continue
            i += 1
        return starts

    def chunk(self, content: str, chunk_size_bytes: int) -> list[str]:
        lines = content.splitlines(keepends=True)
        starts = self._find_section_starts(lines)

        if not starts:
            return _generic_line_chunk(content, chunk_size_bytes)

        sections: list[str] = []
        if starts[0] > 0:
            sections.append("".join(lines[: starts[0]]))
        for idx, start in enumerate(starts):
            end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
            sections.append("".join(lines[start:end]))

        return self._pack(sections, chunk_size_bytes)

    def _pack(self, sections: list[str], chunk_size_bytes: int) -> list[str]:
        chunks: list[str] = []
        current_parts: list[str] = []
        current_size = 0
        last_title = ""

        for section in sections:
            section_bytes = len(section.encode("utf-8", errors="replace"))

            if section_bytes > chunk_size_bytes:
                if current_parts:
                    chunks.append("".join(current_parts))
                    current_parts = []
                    current_size = 0
                chunks.extend(_generic_line_chunk(section, chunk_size_bytes))
                continue

            if current_parts and current_size + section_bytes > chunk_size_bytes:
                chunks.append("".join(current_parts))
                current_parts = [last_title] if last_title else []
                current_size = len(last_title.encode("utf-8", errors="replace"))

            # Capture the title (first 1–3 lines of a section) for overlap.
            head_lines = section.splitlines(keepends=True)[:3]
            last_title = "".join(head_lines)

            current_parts.append(section)
            current_size += section_bytes

        if current_parts:
            chunks.append("".join(current_parts))

        return [_truncate_chunk(c, chunk_size_bytes) for c in chunks] or [content]


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------

class PlainTextChunker(DocChunker):
    """Split plain text at paragraph boundaries (blank lines)."""

    _PARA_SEP = re.compile(r"\n{2,}")

    def chunk(self, content: str, chunk_size_bytes: int) -> list[str]:
        raw_paras = self._PARA_SEP.split(content)
        if not raw_paras:
            return _generic_line_chunk(content, chunk_size_bytes)

        # Re-attach the double-newline separator so paragraphs remain readable.
        paragraphs = [p + "\n\n" for p in raw_paras]
        if paragraphs:
            paragraphs[-1] = paragraphs[-1].rstrip("\n")

        chunks: list[str] = []
        current_parts: list[str] = []
        current_size = 0

        for para in paragraphs:
            para_bytes = len(para.encode("utf-8", errors="replace"))

            if para_bytes > chunk_size_bytes:
                if current_parts:
                    chunks.append("".join(current_parts))
                    current_parts = []
                    current_size = 0
                chunks.extend(_generic_line_chunk(para, chunk_size_bytes))
                continue

            if current_parts and current_size + para_bytes > chunk_size_bytes:
                chunks.append("".join(current_parts))
                # Carry the last paragraph as overlap context.
                last = current_parts[-1]
                current_parts = [last]
                current_size = len(last.encode("utf-8", errors="replace"))

            current_parts.append(para)
            current_size += para_bytes

        if current_parts:
            chunks.append("".join(current_parts))

        return [_truncate_chunk(c, chunk_size_bytes) for c in chunks] or [content]


# ---------------------------------------------------------------------------
# Registry and dispatch
# ---------------------------------------------------------------------------

#: Map doc-type name → chunker class.  Add new entries here to extend support.
_CHUNKER_REGISTRY: dict[str, type[DocChunker]] = {
    "markdown": MarkdownChunker,
    "rst": RSTChunker,
    "plaintext": PlainTextChunker,
}

#: Map file extension (lowercase, with dot) → doc-type name.
_EXTENSION_TO_DOC_TYPE: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".txt": "plaintext",
    ".text": "plaintext",
}


def get_doc_chunker(file_path: str) -> DocChunker:
    """Return the appropriate :class:`DocChunker` for *file_path*.

    Falls back to :class:`PlainTextChunker` for unrecognised extensions.
    """
    _, ext = os.path.splitext(file_path)
    doc_type = _EXTENSION_TO_DOC_TYPE.get(ext.lower(), "plaintext")
    chunker_cls = _CHUNKER_REGISTRY.get(doc_type, PlainTextChunker)
    logger.debug("Using %s for %s", chunker_cls.__name__, file_path)
    return chunker_cls()


def chunk_doc_content(content: str, chunk_size_bytes: int, file_path: str) -> list[str]:
    """Chunk *content* using the chunker best suited for *file_path*'s type."""
    return get_doc_chunker(file_path).chunk(content, chunk_size_bytes)
