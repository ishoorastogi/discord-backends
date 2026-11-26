BEGIN;

-- Brotherhood Bot
GRANT USAGE ON SCHEMA public TO brotherhood_bot;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.users
TO brotherhood_bot;


-- Internship Bot
GRANT USAGE ON SCHEMA public TO internship_bot;

GRANT SELECT, INSERT, UPDATE
ON TABLE
    public.users,
    public.resumes,
    public.internships,
    public.matches
TO internship_bot;


-- Finance Service
GRANT USAGE ON SCHEMA public TO finance_user;

GRANT SELECT
ON TABLE public.users
TO finance_user;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.finances
TO finance_user;

-- Internship Bot sequence permissions
GRANT USAGE
ON SEQUENCE
    public.internships_id_seq,
    public.matches_match_id_seq
TO internship_bot;

-- Finance Service sequence permissions
GRANT USAGE
ON SEQUENCE public.finances_finance_id_seq
TO finance_user;

COMMIT;