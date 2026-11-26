-- Run only in an empty, disposable database with ON_ERROR_STOP enabled.
CREATE EXTENSION vector;
CREATE TABLE public.users (user_id BIGINT PRIMARY KEY);
CREATE TABLE public.resumes (
    user_id BIGINT PRIMARY KEY REFERENCES public.users ON DELETE CASCADE,
    resume_text VECTOR(384),
    skills VECTOR(384),
    experience VECTOR(384),
    education VECTOR(384)
);
CREATE INDEX resumes_vector_idx ON public.resumes USING hnsw (resume_text vector_cosine_ops);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.resumes TO internship_bot;
CREATE TABLE public.internships (id INT PRIMARY KEY, title TEXT);
INSERT INTO public.internships VALUES (7, 'Preserve this posting');
INSERT INTO public.users VALUES (1), (2);
INSERT INTO public.resumes VALUES
    (1, array_fill(1::real, ARRAY[384])::vector, array_fill(2::real, ARRAY[384])::vector,
        array_fill(3::real, ARRAY[384])::vector, array_fill(4::real, ARRAY[384])::vector),
    (2, NULL, array_fill(5::real, ARRAY[384])::vector, NULL, NULL);

CREATE TEMP TABLE original_vectors AS SELECT * FROM public.resumes;
CREATE TEMP TABLE original_relations AS
SELECT oid, relname, relowner, relacl FROM pg_class
WHERE oid IN ('public.resumes'::regclass, 'public.resumes_vector_idx'::regclass,
              'public.internships'::regclass, 'public.users'::regclass);
CREATE TEMP TABLE original_constraints AS
SELECT oid, pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE conrelid = 'public.resumes'::regclass;

\ir ../migrations/001_resume_vector_columns.sql
\ir ../migrations/001_resume_vector_columns.sql

DO $test$
BEGIN
    IF EXISTS (
        SELECT FROM original_vectors old FULL JOIN public.resumes r USING (user_id)
        WHERE old.user_id IS NULL OR r.user_id IS NULL
           OR ROW(r.overall_vector, r.skills_vector, r.experience_vector, r.education_vector)
              IS DISTINCT FROM ROW(old.resume_text, old.skills, old.experience, old.education)
           OR r.titles_vector IS NOT NULL OR r.projects_vector IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Migration changed existing vectors or row count';
    END IF;

    IF (SELECT count(*) FROM pg_attribute
        WHERE attrelid = 'public.resumes'::regclass
          AND attnum > 0 AND NOT attisdropped AND atttypid = 'vector'::regtype
          AND atttypmod = 384) <> 6 THEN
        RAISE EXCEPTION 'Expected six 384-dimensional vectors';
    END IF;

    IF pg_get_indexdef('public.resumes_vector_idx'::regclass) NOT LIKE '%(overall_vector vector_cosine_ops)' THEN
        RAISE EXCEPTION 'Resume cosine index did not follow overall_vector';
    END IF;

    IF EXISTS (
        SELECT FROM original_relations original LEFT JOIN pg_class current USING (oid)
        WHERE ROW(current.relname, current.relowner, current.relacl)
              IS DISTINCT FROM ROW(original.relname, original.relowner, original.relacl)
    ) OR EXISTS (
        SELECT FROM original_constraints original LEFT JOIN pg_constraint current USING (oid)
        WHERE pg_get_constraintdef(current.oid) IS DISTINCT FROM original.definition
    ) THEN
        RAISE EXCEPTION 'Migration changed relation identity, ownership, permissions, or constraints';
    END IF;

    IF (SELECT title FROM public.internships WHERE id = 7) IS DISTINCT FROM 'Preserve this posting' THEN
        RAISE EXCEPTION 'Migration changed unrelated data';
    END IF;
END;
$test$;
