-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Test vector operations
SELECT '[1,2,3]'::vector <-> '[4,5,6]'::vector as test_distance;

-- Verify installation
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
