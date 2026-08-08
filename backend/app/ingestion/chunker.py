"""Split documents into chunks small enough to embed and retrieve precisely.

Chunks are sized in tokens, not characters, because the embedding model has a
token budget and token counts vary wildly between prose and code.
"""

from dataclasses import dataclass

import tiktoken

from app.ingestion.sources import SourceDocument

# Roughly one to two screens of text: big enough to hold a complete thought,
# small enough that a retrieved chunk is mostly relevant to the question.
TARGET_TOKENS = 500

# Carried from the end of one chunk into the start of the next, so an answer
# that straddles a boundary survives in at least one chunk.
OVERLAP_TOKENS = 60

# A *fragment* this small is almost always a heading or stray line. A short
# document that fits in one chunk is kept regardless -- see chunk_text.
MIN_CHUNK_TOKENS = 20

# Even a whole document needs some substance to be worth embedding.
MIN_DOCUMENT_TOKENS = 8

# text-embedding-3-small uses the cl100k_base tokenizer.
_encoder = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class Chunk:
    """A slice of a SourceDocument, ready to embed."""

    source: str
    repo: str
    file_path: str
    chunk_type: str
    source_url: str
    content: str


def count_tokens(text: str) -> int:
    """Return the number of tokens in a string."""
    return len(_encoder.encode(text))


def _split_into_blocks(text: str) -> list[str]:
    """Break text into paragraph-ish blocks, preserving blank-line structure.

    Splitting on blank lines keeps markdown sections and code functions
    intact far more often than splitting on a fixed character count.
    """
    blocks: list[str] = []
    current: list[str] = []

    for line in text.splitlines():
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current))

    return blocks


def _split_oversized_block(block: str) -> list[str]:
    """Split a single block that exceeds the target size, by token count.

    Rare, but happens with minified-ish source files or very long tables.
    """
    token_ids = _encoder.encode(block)
    pieces: list[str] = []

    for start in range(0, len(token_ids), TARGET_TOKENS):
        piece_ids = token_ids[start : start + TARGET_TOKENS]
        pieces.append(_encoder.decode(piece_ids))

    return pieces


def _overlap_tail(text: str) -> str:
    """Return the last OVERLAP_TOKENS worth of text, for the next chunk's head."""
    token_ids = _encoder.encode(text)
    if len(token_ids) <= OVERLAP_TOKENS:
        return text
    return _encoder.decode(token_ids[-OVERLAP_TOKENS:])


def chunk_text(text: str) -> list[str]:
    """Split text into ~TARGET_TOKENS chunks with a small overlap."""
    blocks: list[str] = []
    for block in _split_into_blocks(text):
        if count_tokens(block) > TARGET_TOKENS:
            blocks.extend(_split_oversized_block(block))
        else:
            blocks.append(block)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = count_tokens(block)

        # Adding this block would overflow, so close off the current chunk.
        if current_parts and current_tokens + block_tokens > TARGET_TOKENS:
            chunk = "\n\n".join(current_parts)
            chunks.append(chunk)

            carry = _overlap_tail(chunk)
            current_parts = [carry]
            current_tokens = count_tokens(carry)

        current_parts.append(block)
        current_tokens += block_tokens

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    cleaned = [chunk.strip() for chunk in chunks if chunk.strip()]

    # A document short enough to fit in a single chunk is complete content, not
    # a leftover fragment, so it survives the fragment threshold. Applying
    # MIN_CHUNK_TOKENS here would silently discard small-but-useful files.
    if len(cleaned) == 1:
        return cleaned if count_tokens(cleaned[0]) >= MIN_DOCUMENT_TOKENS else []

    return [chunk for chunk in cleaned if count_tokens(chunk) >= MIN_CHUNK_TOKENS]


def chunk_document(document: SourceDocument) -> list[Chunk]:
    """Split one SourceDocument into embeddable chunks."""
    return [
        Chunk(
            source=document.source,
            repo=document.repo,
            file_path=document.file_path,
            chunk_type=document.chunk_type,
            source_url=document.source_url,
            content=content,
        )
        for content in chunk_text(document.text)
    ]


def chunk_documents(documents: list[SourceDocument]) -> list[Chunk]:
    """Split many documents into a single flat list of chunks."""
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return chunks
