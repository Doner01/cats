-- =======================================================
-- CatRank Complete Supabase Database Schema & Migrations
-- =======================================================

-- 1. Cats Table
CREATE TABLE IF NOT EXISTS public.cats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    user_name TEXT NOT NULL DEFAULT 'Cat Lover',
    user_avatar TEXT,
    name TEXT NOT NULL,
    bio TEXT,
    image_url TEXT NOT NULL,
    likes_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Ensure cat profile columns exist
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS user_avatar TEXT;
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS bio TEXT;

-- 2. Likes Table
CREATE TABLE IF NOT EXISTS public.likes (\
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cat_id UUID NOT NULL REFERENCES public.cats(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE(cat_id, user_id)
);

-- 3. Comments & Threaded Replies Table
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

-- Ensure all columns exist on comments
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_avatar TEXT;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_email TEXT;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES public.comments(id) ON DELETE CASCADE;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS reply_to_name TEXT;

-- 4. Notifications Table
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

-- Ensure all columns exist on notifications
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS actor_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS actor_avatar TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS cat_name TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS cat_image TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT false;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS comment_id UUID;

-- 5. Row Level Security (RLS) policies
ALTER TABLE public.cats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.likes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Allow public read access
CREATE POLICY IF NOT EXISTS "Allow public read on cats" ON public.cats FOR SELECT USING (true);
CREATE POLICY IF NOT EXISTS "Allow public read on comments" ON public.comments FOR SELECT USING (true);
CREATE POLICY IF NOT EXISTS "Allow public read on likes" ON public.likes FOR SELECT USING (true);

-- Allow authenticated users to perform operations
CREATE POLICY IF NOT EXISTS "Allow authenticated insert on cats" ON public.cats FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY IF NOT EXISTS "Allow authenticated insert on comments" ON public.comments FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY IF NOT EXISTS "Allow authenticated insert on likes" ON public.likes FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY IF NOT EXISTS "Allow authenticated read own notifications" ON public.notifications FOR SELECT USING (auth.uid() = user_id);
