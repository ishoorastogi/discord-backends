-- Internship Bot database schema
-- Requires Postgres with the pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

-- Drop in reverse order of dependency so the file can be re-run while testing
DROP TABLE IF EXISTS finances, matches, resumes, internships, users CASCADE;

CREATE TABLE users (
    discord_id  TEXT PRIMARY KEY,
    name        TEXT,
    major       TEXT,
    grad_year   INT,
    phone       TEXT,
    email       TEXT,
    employer    TEXT
);

-- Every resume field is stored as a vector
-- PLACEHOLDER: 384 must match the embedding model's dimension
CREATE TABLE resumes (
    discord_id   TEXT PRIMARY KEY REFERENCES users(discord_id) ON DELETE CASCADE,
    resume_text  vector(384),
    skills       vector(384),
    experience   vector(384),
    education    vector(384)
);

CREATE TABLE internships (
    id            SERIAL PRIMARY KEY,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT,
    location      TEXT,
    role_type     TEXT,
    requirements  TEXT,
    url           TEXT UNIQUE,
    embedding     vector(384)  -- PLACEHOLDER: same dimension as resumes
);

CREATE TABLE matches (
    match_id          SERIAL PRIMARY KEY,
    discord_id        TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    internship_id     INT  NOT NULL REFERENCES internships(id) ON DELETE CASCADE,
    similarity_score  REAL,
    UNIQUE (discord_id, internship_id)
);

CREATE TABLE finances (
    finance_id  SERIAL PRIMARY KEY,
    discord_id  TEXT REFERENCES users(discord_id) ON DELETE SET NULL,
    type        TEXT NOT NULL CHECK (type IN ('income', 'expense', 'dues')),
    amount      NUMERIC(10, 2) NOT NULL CHECK (amount > 0)
);

-- Vector indexes for fast similarity search
CREATE INDEX resumes_vector_idx
    ON resumes USING hnsw (resume_text vector_cosine_ops);
CREATE INDEX internships_embedding_idx
    ON internships USING hnsw (embedding vector_cosine_ops);

-- Open tables
GRANT SELECT, INSERT, UPDATE, DELETE
    ON users, resumes, internships, matches TO PUBLIC;
GRANT USAGE ON SEQUENCE internships_id_seq, matches_match_id_seq TO PUBLIC;

-- Locked table
REVOKE ALL ON finances FROM PUBLIC;
REVOKE ALL ON SEQUENCE finances_finance_id_seq FROM PUBLIC;
