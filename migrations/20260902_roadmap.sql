BEGIN;

-- updated_at is now created in phone_comments.sql
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS reply_to_id uuid REFERENCES public.comments(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_comments_page ON public.comments (cat_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_comments_user_recent ON public.comments (user_id, cat_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_email_lower ON public.profiles (lower(email));

-- handle_new_user() is defined in phone_comments.sql (with NULLIF for phone-only accounts)

CREATE OR REPLACE FUNCTION public.validate_comment_reply()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.parent_id = NEW.id OR NEW.reply_to_id = NEW.id THEN
        RAISE EXCEPTION 'A comment cannot reply to itself';
    END IF;
    IF NEW.parent_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.comments c WHERE c.id = NEW.parent_id AND c.cat_id = NEW.cat_id
    ) THEN RAISE EXCEPTION 'Reply parent must belong to the same cat'; END IF;
    IF NEW.reply_to_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.comments c WHERE c.id = NEW.reply_to_id AND c.cat_id = NEW.cat_id
    ) THEN RAISE EXCEPTION 'Reply target must belong to the same cat'; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
DROP TRIGGER IF EXISTS check_comment_reply ON public.comments;
CREATE TRIGGER check_comment_reply BEFORE INSERT OR UPDATE OF parent_id, reply_to_id, cat_id ON public.comments
FOR EACH ROW EXECUTE FUNCTION public.validate_comment_reply();
REVOKE ALL ON FUNCTION public.validate_comment_reply() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.cleanup_comment_notifications()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM public.notifications WHERE comment_id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
DROP TRIGGER IF EXISTS before_comment_deleted ON public.comments;
CREATE TRIGGER before_comment_deleted BEFORE DELETE ON public.comments
FOR EACH ROW EXECUTE FUNCTION public.cleanup_comment_notifications();
REVOKE ALL ON FUNCTION public.cleanup_comment_notifications() FROM PUBLIC, anon, authenticated;

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.likes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.profiles, public.cats, public.comments, public.likes, public.notifications FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.profiles, public.cats, public.comments, public.likes, public.notifications TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
