-- =======================================================
-- CatRank Complete Supabase Database Schema & Migrations
-- =======================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

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

ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS user_avatar TEXT;
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.cats ADD COLUMN IF NOT EXISTS bio TEXT;

-- 2. Likes Table
CREATE TABLE IF NOT EXISTS public.likes (
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

ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_avatar TEXT;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS user_email TEXT;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS parent_id UUID;
ALTER TABLE public.comments ADD COLUMN IF NOT EXISTS reply_to_name TEXT;

-- Add the FK only if it doesn't already exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'comments_parent_id_fkey'
          AND conrelid = 'public.comments'::regclass
    ) THEN
        ALTER TABLE public.comments
            ADD CONSTRAINT comments_parent_id_fkey
            FOREIGN KEY (parent_id)
            REFERENCES public.comments(id)
            ON DELETE CASCADE;
    END IF;
END $$;

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

ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS actor_name TEXT DEFAULT 'Cat Lover';
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS actor_avatar TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS cat_name TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS cat_image TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT false;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS comment_id UUID;

-- 5. Row Level Security (RLS)
ALTER TABLE public.cats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.likes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Helper: create policy only when it doesn't already exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'cats'
          AND policyname = 'Allow public read on cats'
    ) THEN
        CREATE POLICY "Allow public read on cats"
        ON public.cats FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'comments'
          AND policyname = 'Allow public read on comments'
    ) THEN
        CREATE POLICY "Allow public read on comments"
        ON public.comments FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'likes'
          AND policyname = 'Allow public read on likes'
    ) THEN
        CREATE POLICY "Allow public read on likes"
        ON public.likes FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'cats'
          AND policyname = 'Allow authenticated insert on cats'
    ) THEN
        CREATE POLICY "Allow authenticated insert on cats"
        ON public.cats FOR INSERT TO authenticated WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'comments'
          AND policyname = 'Allow authenticated insert on comments'
    ) THEN
        CREATE POLICY "Allow authenticated insert on comments"
        ON public.comments FOR INSERT TO authenticated WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'likes'
          AND policyname = 'Allow authenticated insert on likes'
    ) THEN
        CREATE POLICY "Allow authenticated insert on likes"
        ON public.likes FOR INSERT TO authenticated WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'notifications'
          AND policyname = 'Allow authenticated read own notifications'
    ) THEN
        CREATE POLICY "Allow authenticated read own notifications"
        ON public.notifications FOR SELECT TO authenticated USING (auth.uid() = user_id);
    END IF;
END $$;

-- 6. Helpful indexes
CREATE INDEX IF NOT EXISTS idx_cats_created_at
    ON public.cats(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cats_likes_count
    ON public.cats(likes_count DESC);

CREATE INDEX IF NOT EXISTS idx_comments_cat_id
    ON public.comments(cat_id);

CREATE INDEX IF NOT EXISTS idx_comments_parent_id
    ON public.comments(parent_id);

CREATE INDEX IF NOT EXISTS idx_comments_created_at
    ON public.comments(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_likes_cat_user
    ON public.likes(cat_id, user_id);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id
    ON public.notifications(user_id);

CREATE INDEX IF NOT EXISTS idx_notifications_comment_id
    ON public.notifications(comment_id);

-- Done.
