BEGIN;

LOCK TABLE public.resumes IN ACCESS EXCLUSIVE MODE;

ALTER TABLE public.resumes
    ADD COLUMN IF NOT EXISTS titles_vector vector(384),
    ADD COLUMN IF NOT EXISTS projects_vector vector(384);

DO $migration$
DECLARE
    old_column text;
    new_column text;
    old_exists boolean;
    new_exists boolean;
    vector_column text;
BEGIN
    FOR old_column, new_column IN
        SELECT * FROM (VALUES
            ('skills', 'skills_vector'),
            ('experience', 'experience_vector'),
            ('education', 'education_vector'),
            -- The legacy resume-level cosine index used this overall embedding.
            ('resume_text', 'overall_vector')
        ) AS renames(old_name, new_name)
    LOOP
        SELECT EXISTS (
            SELECT FROM pg_attribute
            WHERE attrelid = 'public.resumes'::regclass
              AND attname = old_column AND NOT attisdropped
        ), EXISTS (
            SELECT FROM pg_attribute
            WHERE attrelid = 'public.resumes'::regclass
              AND attname = new_column AND NOT attisdropped
        ) INTO old_exists, new_exists;

        IF old_exists AND new_exists THEN
            RAISE EXCEPTION 'Both public.resumes.% and public.resumes.% exist', old_column, new_column;
        ELSIF old_exists THEN
            EXECUTE format('ALTER TABLE public.resumes RENAME COLUMN %I TO %I', old_column, new_column);
        END IF;
    END LOOP;

    FOREACH vector_column IN ARRAY ARRAY[
        'skills_vector', 'titles_vector', 'experience_vector',
        'projects_vector', 'education_vector', 'overall_vector'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT FROM pg_attribute
            WHERE attrelid = 'public.resumes'::regclass
              AND attname = vector_column AND NOT attisdropped
              AND atttypid = 'vector'::regtype AND atttypmod = 384
        ) THEN
            RAISE EXCEPTION 'Expected public.resumes.% to be vector(384)', vector_column;
        END IF;
    END LOOP;
END;
$migration$;

COMMIT;
