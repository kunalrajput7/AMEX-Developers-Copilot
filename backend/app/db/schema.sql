-- Knowledge base schema. Applied automatically on API startup.
-- Safe to run repeatedly: every statement is IF NOT EXISTS.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,

    -- Where this chunk came from.
    source       TEXT NOT NULL,          -- adapter name, e.g. 'github'
    repo         TEXT NOT NULL,          -- e.g. 'americanexpress/nodes'
    file_path    TEXT NOT NULL,          -- path in repo, or 'issue/123'
    chunk_type   TEXT NOT NULL,          -- 'doc' | 'code' | 'issue'
    source_url   TEXT NOT NULL,          -- clickable link, used for citations

    -- The chunk itself.
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,   -- lets re-ingestion skip unchanged chunks
    embedding    VECTOR(1536),           -- text-embedding-3-small = 1536 dims

    -- Keyword-search vector. GENERATED means Postgres maintains it for us,
    -- so it can never drift out of sync with `content`.
    tsv          TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,

    -- Set on every ingestion run; used to delete chunks whose source file
    -- no longer exists (see ingest.py stale cleanup).
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Semantic search: approximate nearest neighbour over the embedding.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Keyword search: exact identifiers, header names, error codes.
CREATE INDEX IF NOT EXISTS idx_chunks_tsv
    ON chunks USING gin (tsv);

-- Tool filtering (search_docs / search_code / search_issues) and stale cleanup.
CREATE INDEX IF NOT EXISTS idx_chunks_type ON chunks (chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_repo ON chunks (repo);
