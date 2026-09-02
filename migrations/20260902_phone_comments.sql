BEGIN;

ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS likes_count integer NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS public.comment_likes (
    comment_id uuid NOT NULL REFERENCES public.comments(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (comment_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_comment_likes_user ON public.comment_likes(user_id, comment_id);
ALTER TABLE public.comment_likes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.comment_likes FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.comment_likes TO service_role;

CREATE OR REPLACE FUNCTION public.refresh_comment_likes_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        UPDATE public.comments SET likes_count = GREATEST(0, likes_count - 1) WHERE id = OLD.comment_id;
        RETURN OLD;
    END IF;
    UPDATE public.comments SET likes_count = likes_count + 1 WHERE id = NEW.comment_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
DROP TRIGGER IF EXISTS on_comment_like_count_change ON public.comment_likes;
CREATE TRIGGER on_comment_like_count_change AFTER INSERT OR DELETE ON public.comment_likes
FOR EACH ROW EXECUTE FUNCTION public.refresh_comment_likes_count();
REVOKE ALL ON FUNCTION public.refresh_comment_likes_count() FROM PUBLIC, anon, authenticated;

UPDATE public.comments c SET likes_count = (SELECT count(*)::integer FROM public.comment_likes l WHERE l.comment_id=c.id);

CREATE OR REPLACE FUNCTION public.set_comment_like(p_comment_id uuid, p_user_id uuid, p_liked boolean)
RETURNS TABLE(liked boolean, likes_count integer, cat_id uuid) AS $$
BEGIN
    PERFORM 1 FROM public.comments c WHERE c.id=p_comment_id FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF p_liked THEN
        INSERT INTO public.comment_likes(comment_id,user_id) VALUES(p_comment_id,p_user_id)
        ON CONFLICT (comment_id,user_id) DO NOTHING;
    ELSE
        DELETE FROM public.comment_likes l WHERE l.comment_id=p_comment_id AND l.user_id=p_user_id;
    END IF;
    RETURN QUERY SELECT p_liked, c.likes_count, c.cat_id FROM public.comments c WHERE c.id=p_comment_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
REVOKE ALL ON FUNCTION public.set_comment_like(uuid,uuid,boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_comment_like(uuid,uuid,boolean) TO service_role;

CREATE OR REPLACE FUNCTION public.edit_comment_with_window(p_comment_id uuid, p_user_id uuid, p_comment text, p_admin boolean DEFAULT false)
RETURNS TABLE(status text, cat_id uuid, comment text, updated_at timestamptz) AS $$
DECLARE
    target public.comments%ROWTYPE;
    edit_time timestamptz;
BEGIN
    SELECT c.* INTO target FROM public.comments c WHERE c.id=p_comment_id FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF NOT p_admin AND target.user_id IS DISTINCT FROM p_user_id THEN
        RETURN QUERY SELECT 'forbidden'::text,target.cat_id,target.comment,target.updated_at;
        RETURN;
    END IF;
    edit_time := clock_timestamp();
    IF NOT p_admin AND edit_time >= target.created_at + interval '2 minutes' THEN
        RETURN QUERY SELECT 'expired'::text,target.cat_id,target.comment,target.updated_at;
        RETURN;
    END IF;
    IF p_comment IS NULL OR char_length(btrim(p_comment)) NOT BETWEEN 1 AND 300 THEN
        RAISE EXCEPTION 'Invalid comment length';
    END IF;
    UPDATE public.comments c SET comment=btrim(p_comment),updated_at=edit_time WHERE c.id=p_comment_id;
    RETURN QUERY SELECT 'updated'::text,target.cat_id,btrim(p_comment),edit_time;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
REVOKE ALL ON FUNCTION public.edit_comment_with_window(uuid,uuid,text,boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.edit_comment_with_window(uuid,uuid,text,boolean) TO service_role;

-- Phone-only accounts have no email; their public identity must never expose their number.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles(id,email,display_name,phone,bio,avatar_url,role)
    VALUES(NEW.id,NULLIF(NEW.email,''),
        left(COALESCE(NULLIF(btrim(NEW.raw_user_meta_data->>'display_name'),''),
                      NULLIF(btrim(NEW.raw_user_meta_data->>'full_name'),''),
                      NULLIF(btrim(NEW.raw_user_meta_data->>'name'),''),
                      NULLIF(split_part(NEW.email,'@',1),''),'Cat Lover'),40),
        left(NULLIF(btrim(NEW.raw_user_meta_data->>'phone_number'),''),30),
        left(NULLIF(btrim(NEW.raw_user_meta_data->>'bio'),''),150),NULL,'user')
    ON CONFLICT(id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;

COMMIT;
