BEGIN;

CREATE TABLE IF NOT EXISTS public.favorites (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    cat_id UUID NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, cat_id)
);

CREATE INDEX IF NOT EXISTS favorites_user_created_idx
    ON public.favorites (user_id, created_at DESC, cat_id);
CREATE INDEX IF NOT EXISTS favorites_cat_idx ON public.favorites (cat_id);

ALTER TABLE public.favorites ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.favorites FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.favorites TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;
