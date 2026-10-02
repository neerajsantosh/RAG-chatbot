-- Migration: 0003_vector_extension.sql
-- Adds vector extension and column for embeddings

CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to chunk table (nullable, filled in Phase 3)
ALTER TABLE chunk ADD COLUMN IF NOT EXISTS embedding VECTOR(384);

-- Add embedding column to document table (nullable)
ALTER TABLE document ADD COLUMN IF NOT EXISTS embedding VECTOR(384);

-- Index for approximate nearest-neighbour search using HNSW
CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hnsw 
ON chunk USING hnsw (embedding vector_cosine_ops);

-- Index for document embeddings
CREATE INDEX IF NOT EXISTS idx_document_embedding_hnsw 
ON document USING hnsw (embedding vector_cosine_ops);

-- GIN index for full-text search on chunk text
CREATE INDEX IF NOT EXISTS idx_chunk_text_gin 
ON chunk USING gin (to_tsvector('english', text));

-- Update document content_hash to be NOT NULL (validated in Phase 3)
ALTER TABLE document ALTER COLUMN content_hash SET NOT NULL;