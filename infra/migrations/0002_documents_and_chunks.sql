-- Migration: 0002_documents_and_chunks.sql
-- Creates document, chunk, and source tables for Phase 2

CREATE TABLE IF NOT EXISTS source (
    id SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL UNIQUE,
    hash TEXT NOT NULL,
    acl_tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES source(id) ON DELETE CASCADE,
    title TEXT,
    body TEXT,
    acl_tags TEXT[] DEFAULT '{}',
    visibility TEXT DEFAULT 'public',
    content_hash TEXT NOT NULL,
    embedding VECTOR(384) NULL,  -- nullable until Phase 3
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunk (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES document(id) ON DELETE CASCADE,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    text TEXT NOT NULL,
    acl_tags TEXT[] DEFAULT '{}',
    embedding VECTOR(384) NULL,  -- nullable until Phase 3
    content_hash TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_chunk_document_id ON chunk(document_id);
CREATE INDEX IF NOT EXISTS idx_chunk_active ON chunk(active);
CREATE INDEX IF NOT EXISTS idx_document_source_id ON document(source_id);
CREATE INDEX IF NOT EXISTS idx_source_hash ON source(hash);