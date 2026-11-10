-- ============================================================
-- TTKZ DATABASE SCHEMA
-- PostgreSQL 17 + pgvector
-- ============================================================

-- Required extension
CREATE EXTENSION IF NOT EXISTS vector;


-- ============================================================
-- TABLE CLEANUP
-- ============================================================

-- WARNING:
-- Dropping tables permanently deletes their records.
-- This schema is intended for initializing a fresh database.
-- Use migrations to modify an existing database.

DROP TABLE IF EXISTS
    finances,
    matches,
    resumes,
    internships,
    users
CASCADE;


-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE users (
    user_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    discord_id          TEXT UNIQUE,
    name                TEXT,
    email               TEXT,
    phone               TEXT,
    class               TEXT,
    major               TEXT,
    grad_year           INT,
    positions_held      TEXT,
    family_line         TEXT,
    nicknames           TEXT,
    brotherhood_status  TEXT,
    linkedin_link       TEXT,
    big                 TEXT,
    littles             TEXT[],
    employer            TEXT
);


-- ============================================================
-- RESUMES
-- ============================================================

-- Vector dimensions must match the embedding model.
-- Currently using 384 dimensions.

CREATE TABLE resumes (
    user_id      BIGINT PRIMARY KEY
                 REFERENCES users(user_id)
                 ON DELETE CASCADE,

    resume_text  vector(384),
    skills       vector(384),
    experience   vector(384),
    education    vector(384)
);


-- ============================================================
-- INTERNSHIPS
-- ============================================================

CREATE TABLE internships (
    id            SERIAL PRIMARY KEY,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT,
    location      TEXT,
    role_type     TEXT,
    requirements  TEXT,
    url           TEXT UNIQUE,
    embedding     vector(384)
);


-- ============================================================
-- MATCHES
-- ============================================================

CREATE TABLE matches (
    match_id          SERIAL PRIMARY KEY,

    user_id           BIGINT NOT NULL
                      REFERENCES users(user_id)
                      ON DELETE CASCADE,

    internship_id     INT NOT NULL
                      REFERENCES internships(id)
                      ON DELETE CASCADE,

    similarity_score  REAL,

    UNIQUE (user_id, internship_id)
);


-- ============================================================
-- FINANCES
-- ============================================================

CREATE TABLE finances (
    finance_id  SERIAL PRIMARY KEY,

    user_id     BIGINT
                REFERENCES users(user_id)
                ON DELETE SET NULL,

    type        TEXT NOT NULL
                CHECK (type IN ('income', 'expense', 'dues')),

    amount      NUMERIC(10, 2) NOT NULL
                CHECK (amount > 0)
);


-- ============================================================
-- VECTOR INDEXES
-- ============================================================

-- HNSW indexes accelerate vector similarity searches.

CREATE INDEX resumes_vector_idx
    ON resumes
    USING hnsw (resume_text vector_cosine_ops);

CREATE INDEX internships_embedding_idx
    ON internships
    USING hnsw (embedding vector_cosine_ops);


-- ============================================================
-- DATABASE ACCESS CONTROL
-- ============================================================

-- Remove broad public access to application tables.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;

-- Remove broad public access to sequences.
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;


-- ============================================================
-- BROTHERHOOD BOT PERMISSIONS
-- ============================================================

-- Allow access to the public schema.
GRANT USAGE ON SCHEMA public TO brotherhood_bot;

-- Allow management of user records.
GRANT SELECT, INSERT, UPDATE, DELETE
ON users
TO brotherhood_bot;

-- Allow automatic generation of user IDs.
GRANT USAGE, SELECT
ON SEQUENCE users_user_id_seq
TO brotherhood_bot;


-- ============================================================
-- FINANCE USER PERMISSIONS
-- ============================================================

-- Allow access to the public schema.
GRANT USAGE ON SCHEMA public TO finance_user;

-- Allow reading user information.
GRANT SELECT
ON users
TO finance_user;

-- Allow management of financial records.
GRANT SELECT, INSERT, UPDATE, DELETE
ON finances
TO finance_user;

-- Locked table
REVOKE ALL ON finances FROM PUBLIC;
REVOKE ALL ON SEQUENCE finances_finance_id_seq FROM PUBLIC;

-- ============================================================
-- INTERNSHIP BOT PERMISSIONS
-- ============================================================

-- Allow access to the public schema.
GRANT USAGE ON SCHEMA public TO internship_bot;

-- Allow reading user information.
GRANT SELECT
ON users
TO internship_bot;

-- Allow management of resumes.
GRANT SELECT, INSERT, UPDATE, DELETE
ON resumes
TO internship_bot;

-- Allow management of internships.
GRANT SELECT, INSERT, UPDATE, DELETE
ON internships
TO internship_bot;

-- Allow management of matches.
GRANT SELECT, INSERT, UPDATE, DELETE
ON matches
TO internship_bot;

-- Allow automatic generation of internship and match IDs.
GRANT USAGE, SELECT
ON SEQUENCE
    internships_id_seq,
    matches_match_id_seq
TO internship_bot;


-- ============================================================
-- END OF SCHEMA
-- ============================================================