BEGIN;

-- Function to validate a comment reply chain and find the root parent
-- SECURITY INVOKER because we want it to run with the caller's privileges (anon/authenticated)
-- but wait, standard comments table might be readable by anon/authenticated.
-- The previous insert_comment_once used SECURITY DEFINER. 
-- Since we are just reading the comments table, SECURITY INVOKER is preferred.
CREATE OR REPLACE FUNCTION public.validate_comment_reply(p_parent_id uuid, p_cat_id uuid)
RETURNS TABLE (
    is_valid boolean,
    root_id uuid,
    reply_to_name text,
    error_reason text
)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_depth integer := 0;
    v_current_id uuid := p_parent_id;
    v_next_id uuid;
    v_seen uuid[] := ARRAY[p_parent_id];
    v_reply_to_name text;
    v_first_cat_id uuid;
BEGIN
    -- Check if parent exists and belongs to the correct cat
    SELECT cat_id, parent_id, user_name INTO v_first_cat_id, v_next_id, v_reply_to_name
    FROM public.comments
    WHERE id = v_current_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, NULL::uuid, NULL::text, 'Parent comment not found'::text;
        RETURN;
    END IF;

    IF v_first_cat_id != p_cat_id THEN
        RETURN QUERY SELECT false, NULL::uuid, NULL::text, 'Invalid reply target (cat_id mismatch)'::text;
        RETURN;
    END IF;

    v_current_id := v_next_id;

    -- Traverse up the tree to find the root
    WHILE v_current_id IS NOT NULL LOOP
        v_depth := v_depth + 1;
        
        IF v_depth >= 30 THEN
            RETURN QUERY SELECT false, NULL::uuid, NULL::text, 'Reply thread too deep'::text;
            RETURN;
        END IF;

        IF v_current_id = ANY(v_seen) THEN
            RETURN QUERY SELECT false, NULL::uuid, NULL::text, 'Cyclic reply thread detected'::text;
            RETURN;
        END IF;

        v_seen := array_append(v_seen, v_current_id);

        SELECT parent_id, cat_id INTO v_next_id, v_first_cat_id
        FROM public.comments
        WHERE id = v_current_id;

        IF NOT FOUND THEN
            RETURN QUERY SELECT false, NULL::uuid, NULL::text, 'Reply thread broken (ancestor missing)'::text;
            RETURN;
        END IF;

        IF v_first_cat_id != p_cat_id THEN
            RETURN QUERY SELECT false, NULL::uuid, NULL::text, 'Reply thread broken (ancestor cat_id mismatch)'::text;
            RETURN;
        END IF;

        IF v_next_id IS NULL THEN
            -- We found the root! v_current_id is the root.
            EXIT;
        END IF;

        v_current_id := v_next_id;
    END LOOP;

    -- If the original parent had no parent (v_next_id was NULL in the first query),
    -- then the original parent IS the root.
    IF array_length(v_seen, 1) = 1 THEN
        v_current_id := p_parent_id;
    END IF;

    RETURN QUERY SELECT true, v_current_id, COALESCE(v_reply_to_name, 'Cat Lover'), NULL::text;
END;
$$;

-- Add an index for traversing parents if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON public.comments (parent_id);

NOTIFY pgrst, 'reload schema';
COMMIT;
