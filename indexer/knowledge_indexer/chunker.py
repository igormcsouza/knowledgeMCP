from dataclasses import dataclass

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

_HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]

# Fallback for header-less sections (or an article with no headers at all)
# that come out of MarkdownHeaderTextSplitter too large to embed sensibly.
_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1500, chunk_overlap=150
)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    section: str  # concatenated header path, e.g. "ACID > Atomicity"


def chunk_article(article_path: str, content: str) -> list[Chunk]:
    """Split one article's markdown body into chunks for embedding.

    MarkdownHeaderTextSplitter is used first (per PLAN.md 1.2) because it
    keeps code blocks and tables intact under their owning header, unlike a
    naive character splitter; RecursiveCharacterTextSplitter only kicks in
    as a fallback for oversized sections.
    """
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADERS_TO_SPLIT_ON, strip_headers=False
    )
    header_docs = splitter.split_text(content)

    chunks: list[Chunk] = []
    index = 0
    for doc in header_docs:
        section = " > ".join(
            doc.metadata[key]
            for _, key in _HEADERS_TO_SPLIT_ON
            if key in doc.metadata
        )

        # split_text is a no-op passthrough for text already under
        # chunk_size, so this is safe to call unconditionally.
        for piece in _FALLBACK_SPLITTER.split_text(doc.page_content):
            chunks.append(
                Chunk(
                    chunk_id=f"{article_path}#{index}",
                    text=piece,
                    section=section or "",
                )
            )
            index += 1

    return chunks
