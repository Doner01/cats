-- =======================================================
-- CatRank Enhanced Supabase Database Schema & Migrations
-- Complete Security, File Protection, Profiles, Bio, & Admin
-- =======================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Profiles Table
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

-- 2. Cats Table (with name, bio / description, image, likes)
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

-- 3. Likes Table
CREATE TABLE IF NOT EXISTS public.likes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cat_id UUID NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE(cat_id, user_id)
);

-- 4. Comments Table (Threaded Replies Support)
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

-- 5. Notifications Table
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

-- 6. Automatic Profile Creation Trigger on Supabase Auth Sign Up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name, phone, bio, avatar_url, role)
    VALUES (
        new.id,
        new.email,
        COALESCE(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)),
        new.raw_user_meta_data->>'phone_number',
        new.raw_user_meta_data->>'bio',
        new.raw_user_meta_data->>'avatar_url',
        COALESCE(new.raw_user_meta_data->>'role', 'user')
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        display_name = COALESCE(EXCLUDED.display_name, public.profiles.display_name),
        phone = COALESCE(EXCLUDED.phone, public.profiles.phone),
        bio = COALESCE(EXCLUDED.bio, public.profiles.bio),
        avatar_url = COALESCE(EXCLUDED.avatar_url, public.profiles.avatar_url),
        updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 7. Row Level Security (RLS) Policies
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.likes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Clean existing policies
DROP POLICY IF EXISTS "Allow public read on profiles" ON public.profiles;
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
DROP POLICY IF EXISTS "Allow authenticated insert on comments" ON public.comments;
DROP POLICY IF EXISTS "Allow author update on comments" ON public.comments;
DROP POLICY IF EXISTS "Allow author or cat owner delete on comments" ON public.comments;

DROP POLICY IF EXISTS "Allow authenticated read own notifications" ON public.notifications;
DROP POLICY IF EXISTS "Allow authenticated update own notifications" ON public.notifications;
DROP POLICY IF EXISTS "Allow authenticated delete own notifications" ON public.notifications;

-- Profiles Policies
CREATE POLICY "Allow public read on profiles" ON public.profiles FOR SELECT USING (true);
CREATE POLICY "Allow authenticated insert own profile" ON public.profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = id);
CREATE POLICY "Allow authenticated update own profile" ON public.profiles FOR UPDATE TO authenticated USING (auth.uid() = id);

-- Cats Policies
CREATE POLICY "Allow public read on cats" ON public.cats FOR SELECT USING (true);
CREATE POLICY "Allow authenticated insert on cats" ON public.cats FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Allow owner update on cats" ON public.cats FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Allow owner delete on cats" ON public.cats FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- Likes Policies
CREATE POLICY "Allow public read on likes" ON public.likes FOR SELECT USING (true);
CREATE POLICY "Allow authenticated insert on likes" ON public.likes FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Allow owner delete on likes" ON public.likes FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- Comments Policies
CREATE POLICY "Allow public read on comments" ON public.comments FOR SELECT USING (true);
CREATE POLICY "Allow authenticated insert on comments" ON public.comments FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Allow author update on comments" ON public.comments FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Allow author or cat owner delete on comments" ON public.comments FOR DELETE TO authenticated USING (
    auth.uid() = user_id OR auth.uid() IN (SELECT user_id FROM public.cats WHERE id = comments.cat_id)
);

-- Notifications Policies
CREATE POLICY "Allow authenticated read own notifications" ON public.notifications FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Allow authenticated update own notifications" ON public.notifications FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Allow authenticated delete own notifications" ON public.notifications FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- 8. Storage Buckets Creation & File Protection Security Policies
INSERT INTO storage.buckets (id, name, public)
VALUES ('cat-images', 'cat-images', true)
ON CONFLICT (id) DO UPDATE SET public = true;

INSERT INTO storage.buckets (id, name, public)
VALUES ('avatars', 'avatars', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Storage Policies
DROP POLICY IF EXISTS "Public Read Cat Images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Upload Own Cat Images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Update Own Cat Images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Delete Own Cat Images" ON storage.objects;

DROP POLICY IF EXISTS "Public Read Avatars" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Upload Own Avatar" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Users Delete Own Avatar" ON storage.objects;

CREATE POLICY "Public Read Cat Images" ON storage.objects FOR SELECT USING (bucket_id = 'cat-images');
CREATE POLICY "Authenticated Users Upload Own Cat Images" ON storage.objects FOR INSERT TO authenticated WITH CHECK (
    bucket_id = 'cat-images' AND (storage.foldername(name))[1] = auth.uid()::text
);
CREATE POLICY "Authenticated Users Update Own Cat Images" ON storage.objects FOR UPDATE TO authenticated USING (
    bucket_id = 'cat-images' AND (storage.foldername(name))[1] = auth.uid()::text
);
CREATE POLICY "Authenticated Users Delete Own Cat Images" ON storage.objects FOR DELETE TO authenticated USING (
    bucket_id = 'cat-images' AND (storage.foldername(name))[1] = auth.uid()::text
);

CREATE POLICY "Public Read Avatars" ON storage.objects FOR SELECT USING (bucket_id = 'avatars');
CREATE POLICY "Authenticated Users Upload Own Avatar" ON storage.objects FOR INSERT TO authenticated WITH CHECK (
    bucket_id = 'avatars' AND ((storage.foldername(name))[1] = auth.uid()::text OR (storage.foldername(name))[2] = auth.uid()::text)
);
CREATE POLICY "Authenticated Users Delete Own Avatar" ON storage.objects FOR DELETE TO authenticated USING (
    bucket_id = 'avatars' AND ((storage.foldername(name))[1] = auth.uid()::text OR (storage.foldername(name))[2] = auth.uid()::text)
);
