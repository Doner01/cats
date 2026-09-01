BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT,
    display_name TEXT NOT NULL DEFAULT 'Cat Lover',
    phone TEXT,
    bio TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS display_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now());

CREATE TABLE IF NOT EXISTS public.cats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    user_name TEXT NOT NULL DEFAULT 'Cat Lover',
    user_avatar TEXT,
    name TEXT NOT NULL,
    bio TEXT,
    description TEXT,
    image_url TEXT NOT NULL,
    likes_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS user_avatar TEXT;
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS description TEXT;

CREATE TABLE IF NOT EXISTS public.likes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cat_id UUID NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE(cat_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cat_id UUID NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    user_name TEXT NOT NULL DEFAULT 'Cat Lover',
    user_avatar TEXT,
    user_email TEXT,
    parent_id UUID REFERENCES public.comments(id) ON DELETE CASCADE,
    reply_to_name TEXT,
    comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_avatar TEXT;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_email TEXT;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES public.comments(id) ON DELETE CASCADE;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS reply_to_name TEXT;

CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    actor_id UUID,
    actor_name TEXT NOT NULL DEFAULT 'Cat Lover',
    actor_avatar TEXT,
    type TEXT NOT NULL DEFAULT 'like',
    cat_id UUID REFERENCES public.cats(id) ON DELETE CASCADE,
    cat_name TEXT,
    cat_image TEXT,
    comment_id UUID,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS actor_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS actor_avatar TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS cat_name TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS cat_image TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT false;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS comment_id UUID;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name, phone, bio, avatar_url, role)
    VALUES (
        new.id,
        new.email,
        left(COALESCE(NULLIF(btrim(new.raw_user_meta_data->>'display_name'), ''), split_part(new.email, '@', 1), 'Cat Lover'), 40),
        left(NULLIF(btrim(new.raw_user_meta_data->>'phone_number'), ''), 30),
        left(NULLIF(btrim(new.raw_user_meta_data->>'bio'), ''), 150),
        NULL,
        'user'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

CREATE OR REPLACE FUNCTION public.sync_profile_email()
RETURNS TRIGGER AS $$
BEGIN
    IF new.email IS DISTINCT FROM old.email THEN
        UPDATE public.profiles
        SET email = new.email, updated_at = timezone('utc'::text, now())
        WHERE id = new.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

DROP TRIGGER IF EXISTS on_auth_user_email_changed ON auth.users;
CREATE TRIGGER on_auth_user_email_changed
    AFTER UPDATE OF email ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.sync_profile_email();

REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.sync_profile_email() FROM PUBLIC, anon, authenticated;

INSERT INTO public.profiles (id, email, display_name, phone, bio, avatar_url, role)
SELECT
    u.id,
    u.email,
    left(COALESCE(NULLIF(btrim(u.raw_user_meta_data->>'display_name'), ''), split_part(u.email, '@', 1), 'Cat Lover'), 40),
    left(NULLIF(btrim(u.raw_user_meta_data->>'phone_number'), ''), 30),
    left(NULLIF(btrim(u.raw_user_meta_data->>'bio'), ''), 150),
    NULL,
    'user'
FROM auth.users u
ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.likes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public read on profiles" ON public.profiles;
DROP POLICY IF EXISTS "Allow authenticated read own profile" ON public.profiles;
DROP POLICY IF EXISTS "Allow authenticated insert own profile" ON public.profiles;
DROP POLICY IF EXISTS "Allow authenticated update own profile" ON public.profiles;

DROP POLICY IF EXISTS "Allow public read on cats" ON public.cats;
DROP POLICY IF EXISTS "Allow authenticated insert on cats" ON public.cats;
DROP POLICY IF EXISTS "Allow owner update on cats" ON public.cats;
DROP POLICY IF EXISTS "Allow owner delete on cats" ON public.cats;

DROP POLICY IF EXISTS "Allow public read on likes" ON public.likes;
DROP POLICY IF EXISTS "Allow authenticated insert on likes" ON public.likes;
DROP POLICY IF EXISTS "Allow owner delete on likes" ON public.likes;

DROP POLICY IF EXISTS "Allow public read on comments" ON public.comments;
DROP POLICY IF EXISTS "Allow authenticated read comments" ON public.comments;
DROP POLICY IF EXISTS "Allow authenticated insert on comments" ON public.comments;
DROP POLICY IF EXISTS "Allow author update on comments" ON public.comments;
DROP POLICY IF EXISTS "Allow author or cat owner delete on comments" ON public.comments;

DROP POLICY IF EXISTS "Allow authenticated read own notifications" ON public.notifications;
DROP POLICY IF EXISTS "Allow authenticated update own notifications" ON public.notifications;
DROP POLICY IF EXISTS "Allow authenticated delete own notifications" ON public.notifications;

REVOKE ALL ON TABLE public.profiles FROM anon, authenticated;
REVOKE ALL ON TABLE public.cats FROM anon, authenticated;
REVOKE ALL ON TABLE public.likes FROM anon, authenticated;
REVOKE ALL ON TABLE public.comments FROM anon, authenticated;
REVOKE ALL ON TABLE public.notifications FROM anon, authenticated;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;

UPDATE public.cats
SET name = left(COALESCE(NULLIF(btrim(name), ''), 'Cat'), 80),
    user_name = left(COALESCE(NULLIF(btrim(user_name), ''), 'Cat Lover'), 40),
    bio = CASE WHEN bio IS NULL THEN NULL ELSE left(bio, 1000) END,
    description = CASE WHEN description IS NULL THEN NULL ELSE left(description, 1000) END,
    likes_count = GREATEST(COALESCE(likes_count, 0), 0);

UPDATE public.comments
SET user_name = left(COALESCE(NULLIF(btrim(user_name), ''), 'Cat Lover'), 40),
    comment = left(COALESCE(NULLIF(btrim(comment), ''), '[removed]'), 300),
    reply_to_name = CASE WHEN reply_to_name IS NULL THEN NULL ELSE left(reply_to_name, 40) END;

UPDATE public.profiles
SET display_name = left(COALESCE(NULLIF(btrim(display_name), ''), 'Cat Lover'), 40),
    phone = CASE WHEN phone IS NULL THEN NULL ELSE left(phone, 30) END,
    bio = CASE WHEN bio IS NULL THEN NULL ELSE left(bio, 150) END;

CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_email_ci
    ON public.profiles (lower(email)) WHERE email IS NOT NULL;

DELETE FROM public.likes a
USING public.likes b
WHERE a.cat_id = b.cat_id AND a.user_id = b.user_id AND a.ctid > b.ctid;
CREATE UNIQUE INDEX IF NOT EXISTS idx_likes_cat_user_unique ON public.likes (cat_id, user_id);

CREATE INDEX IF NOT EXISTS idx_cats_created_at ON public.cats (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cats_likes_created ON public.cats (likes_count DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cats_user_created ON public.cats (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_likes_user_id ON public.likes (user_id);
CREATE INDEX IF NOT EXISTS idx_comments_user_id ON public.comments (user_id);
CREATE INDEX IF NOT EXISTS idx_comments_cat_created ON public.comments (cat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON public.comments (parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON public.notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON public.notifications (user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_actor_id ON public.notifications (actor_id) WHERE actor_id IS NOT NULL;

DO $$
BEGIN
    ALTER TABLE public.cats ADD CONSTRAINT cats_likes_nonnegative CHECK (likes_count >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.cats ADD CONSTRAINT cats_name_length CHECK (char_length(name) BETWEEN 1 AND 80);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.cats ADD CONSTRAINT cats_user_name_length CHECK (char_length(user_name) BETWEEN 1 AND 40);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.cats ADD CONSTRAINT cats_description_length CHECK (description IS NULL OR char_length(description) <= 1000);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.comments ADD CONSTRAINT comments_length CHECK (char_length(comment) BETWEEN 1 AND 300);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.cats ADD CONSTRAINT cats_bio_length CHECK (bio IS NULL OR char_length(bio) <= 1000);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.profiles ADD CONSTRAINT profiles_display_name_length CHECK (char_length(display_name) BETWEEN 1 AND 40);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.profiles ADD CONSTRAINT profiles_bio_length CHECK (bio IS NULL OR char_length(bio) <= 150);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

UPDATE public.profiles SET role = 'user' WHERE role IS NULL OR lower(role) NOT IN ('user', 'admin');
UPDATE public.profiles SET role = lower(role);
ALTER TABLE public.profiles ALTER COLUMN role SET DEFAULT 'user';
ALTER TABLE public.profiles ALTER COLUMN role SET NOT NULL;
DO $$
BEGIN
    ALTER TABLE public.profiles ADD CONSTRAINT profiles_role_valid CHECK (role IN ('user', 'admin'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.profiles ADD CONSTRAINT profiles_phone_length CHECK (phone IS NULL OR char_length(phone) <= 30);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE public.comments ADD CONSTRAINT comments_user_name_length CHECK (char_length(user_name) BETWEEN 1 AND 40);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

UPDATE public.notifications n
SET comment_id = NULL
WHERE comment_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM public.comments c WHERE c.id = n.comment_id);
DO $$
BEGIN
    ALTER TABLE public.notifications
        ADD CONSTRAINT notifications_comment_id_fkey
        FOREIGN KEY (comment_id) REFERENCES public.comments(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION public.refresh_cat_likes_count()
RETURNS TRIGGER AS $$
DECLARE
    target_cat UUID;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_cat := OLD.cat_id;
    ELSE
        target_cat := NEW.cat_id;
    END IF;

    UPDATE public.cats
    SET likes_count = GREATEST(0, likes_count + CASE WHEN TG_OP = 'DELETE' THEN -1 ELSE 1 END)
    WHERE id = target_cat;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

DROP TRIGGER IF EXISTS on_like_count_change ON public.likes;
CREATE TRIGGER on_like_count_change
    AFTER INSERT OR DELETE ON public.likes
    FOR EACH ROW EXECUTE FUNCTION public.refresh_cat_likes_count();
REVOKE ALL ON FUNCTION public.refresh_cat_likes_count() FROM PUBLIC, anon, authenticated;

UPDATE public.cats c
SET likes_count = (SELECT count(*)::integer FROM public.likes l WHERE l.cat_id = c.id);

CREATE OR REPLACE FUNCTION public.toggle_cat_like(p_cat_id UUID, p_user_id UUID)
RETURNS TABLE(action TEXT, likes_count INTEGER) AS $$
DECLARE
    existing_like UUID;
BEGIN
    PERFORM id FROM public.cats WHERE id = p_cat_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cat not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT id INTO existing_like
    FROM public.likes
    WHERE cat_id = p_cat_id AND user_id = p_user_id
    LIMIT 1;

    IF existing_like IS NULL THEN
        INSERT INTO public.likes (cat_id, user_id) VALUES (p_cat_id, p_user_id);
        action := 'liked';
    ELSE
        DELETE FROM public.likes WHERE id = existing_like;
        action := 'unliked';
    END IF;

    SELECT c.likes_count INTO likes_count FROM public.cats c WHERE c.id = p_cat_id;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

REVOKE ALL ON FUNCTION public.toggle_cat_like(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.toggle_cat_like(UUID, UUID) TO service_role;

INSERT INTO storage.buckets (id, name, public)
VALUES ('cat-images', 'cat-images', true)
ON CONFLICT (id) DO UPDATE SET public = true;

INSERT INTO storage.buckets (id, name, public)
VALUES ('avatars', 'avatars', true)
ON CONFLICT (id) DO UPDATE SET public = true;

DROP POLICY IF EXISTS "Public Read Cat Images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Upload Own Cat Images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Update Own Cat Images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Delete Own Cat Images" ON storage.objects;
DROP POLICY IF EXISTS "Public Read Avatars" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Upload Own Avatar" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Delete Own Avatar" ON storage.objects;

REVOKE INSERT, UPDATE, DELETE ON storage.objects FROM anon, authenticated;

CREATE POLICY "Public Read Cat Images" ON storage.objects
    FOR SELECT TO anon, authenticated
    USING (bucket_id = 'cat-images');

CREATE POLICY "Public Read Avatars" ON storage.objects
    FOR SELECT TO anon, authenticated
    USING (bucket_id = 'avatars');

CREATE OR REPLACE FUNCTION public.sync_profile_attribution()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.display_name IS DISTINCT FROM OLD.display_name OR NEW.avatar_url IS DISTINCT FROM OLD.avatar_url THEN
        UPDATE public.cats SET user_name = NEW.display_name, user_avatar = NEW.avatar_url WHERE user_id = NEW.id;
        UPDATE public.comments SET user_name = NEW.display_name, user_avatar = NEW.avatar_url WHERE user_id = NEW.id;
        UPDATE public.notifications SET actor_name = NEW.display_name, actor_avatar = NEW.avatar_url WHERE actor_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
DROP TRIGGER IF EXISTS on_profile_attribution_changed ON public.profiles;
CREATE TRIGGER on_profile_attribution_changed AFTER UPDATE OF display_name, avatar_url ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.sync_profile_attribution();
REVOKE ALL ON FUNCTION public.sync_profile_attribution() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.cleanup_deleted_user()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM public.notifications WHERE user_id = OLD.id OR actor_id = OLD.id;
    DELETE FROM public.comments WHERE user_id = OLD.id;
    DELETE FROM public.likes WHERE user_id = OLD.id;
    DELETE FROM public.cats WHERE user_id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';
DROP TRIGGER IF EXISTS before_auth_user_deleted ON auth.users;
CREATE TRIGGER before_auth_user_deleted BEFORE DELETE ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.cleanup_deleted_user();
REVOKE ALL ON FUNCTION public.cleanup_deleted_user() FROM PUBLIC, anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_cats_feed_order ON public.cats (created_at DESC, id);
GRANT ALL ON TABLE public.profiles, public.cats, public.likes, public.comments, public.notifications TO service_role;

COMMIT;
