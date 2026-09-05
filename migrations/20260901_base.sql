-- Fresh Supabase project baseline. Apply before the 20260902 migrations.
-- Existing projects must compare their historical schema/triggers with this
-- baseline before applying it; CREATE TABLE IF NOT EXISTS is not schema repair.
BEGIN;

CREATE TABLE IF NOT EXISTS public.profiles (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email text,
    display_name text NOT NULL DEFAULT 'Cat Lover',
    avatar_url text,
    phone text,
    bio text,
    role text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.cats (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    user_name text NOT NULL DEFAULT 'Cat Lover',
    user_avatar text,
    name text NOT NULL,
    bio text,
    description text,
    image_url text NOT NULL,
    likes_count integer NOT NULL DEFAULT 0 CHECK (likes_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.likes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cat_id uuid NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (cat_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.comments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cat_id uuid NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    user_name text NOT NULL DEFAULT 'Cat Lover',
    user_avatar text,
    user_email text,
    parent_id uuid REFERENCES public.comments(id) ON DELETE CASCADE,
    reply_to_name text,
    comment text NOT NULL CHECK (char_length(btrim(comment)) BETWEEN 1 AND 300),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    actor_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    actor_name text NOT NULL DEFAULT 'Cat Lover',
    actor_avatar text,
    type text NOT NULL,
    cat_id uuid NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    cat_name text,
    cat_image text,
    comment_id uuid REFERENCES public.comments(id) ON DELETE CASCADE,
    message text NOT NULL,
    is_read boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cats_feed ON public.cats(created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_cats_ranking ON public.cats(likes_count DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cats_user_page ON public.cats(user_id, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_likes_user ON public.likes(user_id, id);
CREATE INDEX IF NOT EXISTS idx_comments_parent ON public.comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_page ON public.notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON public.notifications(user_id) WHERE NOT is_read;
CREATE INDEX IF NOT EXISTS idx_notifications_actor ON public.notifications(actor_id);
CREATE INDEX IF NOT EXISTS idx_notifications_cat ON public.notifications(cat_id);
CREATE INDEX IF NOT EXISTS idx_notifications_comment ON public.notifications(comment_id);

CREATE OR REPLACE FUNCTION public.refresh_cat_likes_count()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        UPDATE public.cats SET likes_count = GREATEST(0, likes_count - 1) WHERE id = OLD.cat_id;
        RETURN OLD;
    END IF;
    UPDATE public.cats SET likes_count = likes_count + 1 WHERE id = NEW.cat_id;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS on_cat_like_count_change ON public.likes;
CREATE TRIGGER on_cat_like_count_change AFTER INSERT OR DELETE ON public.likes
FOR EACH ROW EXECUTE FUNCTION public.refresh_cat_likes_count();
REVOKE ALL ON FUNCTION public.refresh_cat_likes_count() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.toggle_cat_like(p_cat_id uuid, p_user_id uuid)
RETURNS TABLE(action text, likes_count integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    result_action text;
BEGIN
    -- Serialize votes for this cat so concurrent toggles cannot lose increments
    -- or both observe an absent (cat_id, user_id) pair.
    PERFORM 1 FROM public.cats c WHERE c.id = p_cat_id FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    DELETE FROM public.likes l WHERE l.cat_id = p_cat_id AND l.user_id = p_user_id;
    IF FOUND THEN
        result_action := 'unliked';
    ELSE
        INSERT INTO public.likes(cat_id, user_id) VALUES (p_cat_id, p_user_id);
        result_action := 'liked';
    END IF;
    RETURN QUERY SELECT result_action, c.likes_count FROM public.cats c WHERE c.id = p_cat_id;
END;
$$;
REVOKE ALL ON FUNCTION public.toggle_cat_like(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.toggle_cat_like(uuid, uuid) TO service_role;

-- The later phone_comments migration replaces this body with the same profile
-- initialization behavior. The trigger itself must exist on a fresh project.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    INSERT INTO public.profiles(id, email, display_name)
    VALUES (NEW.id, NULLIF(NEW.email, ''),
        left(COALESCE(NULLIF(btrim(NEW.raw_user_meta_data->>'display_name'), ''),
                      NULLIF(btrim(NEW.raw_user_meta_data->>'full_name'), ''),
                      NULLIF(btrim(NEW.raw_user_meta_data->>'name'), ''),
                      NULLIF(split_part(NEW.email, '@', 1), ''), 'Cat Lover'), 40))
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.sync_profile_attribution()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF NEW.display_name IS DISTINCT FROM OLD.display_name OR NEW.avatar_url IS DISTINCT FROM OLD.avatar_url THEN
        UPDATE public.cats SET user_name = NEW.display_name, user_avatar = NEW.avatar_url WHERE user_id = NEW.id;
        UPDATE public.comments SET user_name = NEW.display_name, user_avatar = NEW.avatar_url WHERE user_id = NEW.id;
        UPDATE public.notifications SET actor_name = NEW.display_name, actor_avatar = NEW.avatar_url WHERE actor_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS on_profile_attribution_change ON public.profiles;
CREATE TRIGGER on_profile_attribution_change AFTER UPDATE OF display_name, avatar_url ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.sync_profile_attribution();
REVOKE ALL ON FUNCTION public.sync_profile_attribution() FROM PUBLIC, anon, authenticated;

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.likes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.profiles, public.cats, public.likes, public.comments, public.notifications FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles, public.cats, public.likes, public.comments, public.notifications TO service_role;

-- Public reads use bucket URLs; uploads/deletes remain service-role operations.
-- No authenticated/anonymous storage write policies are installed.
INSERT INTO storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
VALUES ('cat-images', 'cat-images', true, 5242880, ARRAY['image/webp', 'image/gif']),
       ('avatars', 'avatars', true, 5242880, ARRAY['image/webp'])
ON CONFLICT (id) DO NOTHING;

NOTIFY pgrst, 'reload schema';
COMMIT;
