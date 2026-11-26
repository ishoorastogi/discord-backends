BEGIN;

-- Brotherhood Bot
GRANT USAGE ON SCHEMA public TO brotherhood_bot;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.users
TO brotherhood_bot;


-- Internship Bot
GRANT USAGE ON SCHEMA public TO internship_bot;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.users
TO internship_bot;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.resumes
TO internship_bot;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.internships
TO internship_bot;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.matches
TO internship_bot;


-- Finance Service
GRANT USAGE ON SCHEMA public TO finance_user;

GRANT SELECT
ON TABLE public.users
TO finance_user;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.finances
TO finance_user;

COMMIT;