BEGIN;

-- Serialize the duplicate check and insert across workers for one account/cat.
-- Unlike a check in Flask, both operations run in the same transaction.
CREATE OR REPLACE FUNCTION public.insert_comment_once(p_comment jsonb)
RETURNS TABLE(status text, comment_id uuid, created_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    incoming public.comments%ROWTYPE;
    previous public.comments%ROWTYPE;
    inserted_at timestamptz;
BEGIN
    incoming := jsonb_populate_record(NULL::public.comments, p_comment);
    IF incoming.user_id IS NULL OR incoming.cat_id IS NULL OR incoming.id IS NULL
       OR incoming.comment IS NULL OR char_length(btrim(incoming.comment)) NOT BETWEEN 1 AND 300 THEN
        RAISE EXCEPTION 'Invalid comment';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(
        'catrank:comment:' || incoming.user_id::text || ':' || incoming.cat_id::text, 0));
    inserted_at := clock_timestamp();
    SELECT c.* INTO previous FROM public.comments c
    WHERE c.user_id = incoming.user_id AND c.cat_id = incoming.cat_id
      AND c.comment = incoming.comment AND c.created_at >= inserted_at - interval '60 seconds'
    ORDER BY c.created_at DESC LIMIT 1;
    IF FOUND THEN
        RETURN QUERY SELECT 'duplicate'::text, previous.id, previous.created_at;
        RETURN;
    END IF;
    INSERT INTO public.comments(id, cat_id, user_id, user_name, user_avatar,
        user_email, parent_id, reply_to_id, reply_to_name, comment, created_at)
    VALUES (incoming.id, incoming.cat_id, incoming.user_id,
        COALESCE(incoming.user_name, 'Cat Lover'), incoming.user_avatar,
        incoming.user_email, incoming.parent_id, incoming.reply_to_id,
        incoming.reply_to_name, incoming.comment, inserted_at);
    RETURN QUERY SELECT 'inserted'::text, incoming.id, inserted_at;
END;
$$;
REVOKE ALL ON FUNCTION public.insert_comment_once(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.insert_comment_once(jsonb) TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;
