BEGIN;

-- One aggregate result avoids transferring cats and silently summing only the
-- first PostgREST response page. Only the authenticated backend may invoke it.
CREATE OR REPLACE FUNCTION public.admin_overview_counts()
RETURNS TABLE(total_cats bigint, total_likes bigint, total_users bigint, total_comments bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT count(*), COALESCE(sum(c.likes_count), 0)::bigint,
           (SELECT count(*) FROM public.profiles),
           (SELECT count(*) FROM public.comments)
    FROM public.cats c;
$$;
REVOKE ALL ON FUNCTION public.admin_overview_counts() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_overview_counts() TO service_role;

-- Fetch counts for an entire admin page in one query instead of one per user.
CREATE OR REPLACE FUNCTION public.admin_user_counts(p_user_ids uuid[])
RETURNS TABLE(user_id uuid, cats_count bigint, total_likes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT requested.id, count(c.id), COALESCE(sum(c.likes_count), 0)::bigint
    FROM (SELECT DISTINCT unnest(p_user_ids) AS id) requested
    LEFT JOIN public.cats c ON c.user_id = requested.id
    GROUP BY requested.id;
$$;
REVOKE ALL ON FUNCTION public.admin_user_counts(uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_user_counts(uuid[]) TO service_role;

CREATE INDEX IF NOT EXISTS idx_cats_feed ON public.cats (created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_cats_ranking ON public.cats (likes_count DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cats_user_page ON public.cats (user_id, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_page ON public.notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON public.notifications (user_id) WHERE is_read = false;

NOTIFY pgrst, 'reload schema';
COMMIT;
