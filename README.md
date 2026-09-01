# Cat

Final deployment package for the CatRank site.

## What this build includes

- Flask backend with Supabase Auth/PostgreSQL.
- Cloudflare R2 image storage with Supabase Storage fallback.
- Upstash/Redis rate limiting and short-lived application caching.
- Fixed cat viewer with inline expandable bio: **Read full bio** expands inside the existing viewer and **Show less** collapses it. The outer viewer stays the same size.
- Likes, comments, replies, favorites, profiles, notifications, leaderboard, admin tools, image optimization, and security headers.

## Deploy

1. Keep all private values in your hosting provider's environment variables. Never upload or commit a real `.env` file.
2. Copy the values described in `.env.example` into your host. For production use:
   - `APP_ENV=production`
   - a random `SECRET_KEY` of at least 32 characters
   - your HTTPS origin in `PUBLIC_SITE_URL`
   - your Supabase keys
   - your R2 credentials if using R2
   - your working Upstash TCP/TLS `rediss://...` URL in `RATE_LIMIT_STORAGE_URI`
   - optionally set `CACHE_REDIS_URL` to a separate Redis URL; if blank, the app reuses `RATE_LIMIT_STORAGE_URI`
3. For a fresh Supabase database, run `supabase_migration.sql` in the Supabase SQL Editor. If the main schema already exists but the Favorites feature has not been installed yet, run `migrations/20260902_favorites.sql` once instead.
4. In Supabase Auth, enable email confirmation and secure email change. Set your Site URL and allow these redirect URLs:
   - `https://YOUR-DOMAIN/login?confirmed=1`
   - `https://YOUR-DOMAIN/reset-password`
   - `https://YOUR-DOMAIN/profile?email_confirmed=1`
5. Configure SMTP in Supabase for production email delivery.
6. Deploy with the included Dockerfile/Railway configuration, or run:

```sh
gunicorn --config gunicorn.conf.py app:app
```

The app binds to the host-provided `PORT`.

## Redis

Redis is used for shared rate limits and temporary caches. Photos remain in R2/Supabase Storage and permanent app data remains in Supabase. Cached feed/profile/cat/leaderboard entries automatically expire and the application cache falls back to Supabase if Redis cache reads fail.

## Public files and server files

The Flask app only exposes routes you define and files under `/static`. Files such as `app.py`, `.env`, `gunicorn.conf.py`, and other server files are not downloadable as `/app.py`, `/.env`, and similar URLs with this deployment setup. The real `.env` is intentionally not included in this package.

Frontend JavaScript/CSS/fonts under `/static` are public by design, so never place secrets in those files.

## Final checks before launch

Test registration, email confirmation, login/logout, password reset, email change, cat upload/edit/delete, like/unlike, comments/replies, favorites, profile/avatar updates, leaderboard, admin actions, and the site on a phone. Also check deployment logs for unexpected 500 errors.
