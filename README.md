# CatRank — optimized Vercel edition

Complete Python 3.12 / Flask application with Supabase Auth and PostgreSQL, Cloudflare R2 images, and optional Redis caching/rate limits. This is the full project, not an overwrite patch.

## Install

1. Back up the existing project and database. Keep the previous Vercel deployment available for rollback.
2. Extract this ZIP into a **new, clean folder**. Use the folder containing `app.py` and `vercel.json` as the Vercel project root. Extracting over an old folder will not remove its unused files.
3. Keep your existing private Vercel environment values. For local development only, keep your private `.env` outside the ZIP and copy it into the new project folder. Do not upload it or Git history. `.env.example` contains placeholders, not production credentials.
4. Verify the migrations below are installed. This optimization adds **no new database migration** beyond those in the uploaded project.
5. On Vercel select **Flask** and redeploy. The included build command runs `python build_vercel.py`; dependencies are installed from `requirements.txt`. Do not set the project root itself as a public output directory. CSS and JavaScript are already included; no npm build is needed for deployment.
6. Check `/livez` (200) and `/healthz` (200 when the database works), then complete the release checks below. Hard-refresh once if upgrading from an older release.

### Database order

For a fresh database, run `supabase_migration.sql` first. For both fresh and existing installations, run these files in Supabase SQL Editor, in order, if they have not already been applied:

1. `migrations/20260902_favorites.sql`
2. `migrations/20260902_roadmap.sql`
3. `migrations/20260902_phone_comments.sql`

The third migration also enables **comment likes and the two-minute editing rule**; it is required even while phone sign-in is disabled. The scripts can be rerun. Do not drop tables or functions to roll back this app update.

### Production settings

Set each key once. Keep your real Supabase, R2, Redis, administrator email and secret values privately in Vercel.

```dotenv
APP_ENV=production
PUBLIC_SITE_URL=https://cats.octov.uz
ENABLE_DEMO_DATA=false
FLASK_DEBUG=false
TRUST_PROXY_HOPS=1
COUNTRY_ACCESS_ENABLED=false
ALLOWED_COUNTRIES=
PHONE_AUTH_ENABLED=false
```

- `SECRET_KEY`: a random value of at least 32 characters. Generate privately with `python -c "import secrets; print(secrets.token_hex(32))"`. Replace previously exposed secrets in their provider dashboards, then update Vercel.
- Keep `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `ADMIN_EMAILS` and all `R2_*` values. Only the public Supabase URL/key belong in browser code. Never expose the service key, Redis password, or R2 secret.
- Use your working private `rediss://` TCP/TLS URL in `RATE_LIMIT_STORAGE_URI`. The cache reuses it when `CACHE_REDIS_URL` is empty. An HTTPS REST URL is not interchangeable. Redis failure falls back to Supabase reads and per-process memory limits; the fallback is **not a shared limit** across Vercel instances.
- `COUNTRY_ACCESS_ENABLED=false` allows everyone, including unknown locations. Leave `ALLOWED_COUNTRIES` empty. Enabling this optional Vercel-only rule blocks all app pages/APIs outside the allowlist, including existing users; it does not protect public R2 images or direct Supabase Auth endpoints.
- Leave `GOOGLE_AUTH_ENABLED` at its existing working value. If Google is not configured, use `false` until the setup below is complete.
- Use separate Supabase and Redis projects/databases for previews that change data or send messages. Explicitly allow their own auth redirects. Do not point automated tests at production.

## Google, email and phone configuration

### Google

The full-color Google button and PKCE flow are included. A client ID alone does not enable the provider.

1. In Google Cloud, use a Web OAuth client with your site origin. Copy the **exact callback URL shown by Supabase's Google provider** into Google's authorized redirect URIs. It is the Supabase Auth callback, not `/auth/callback` on CatRank.
2. Enable Google in Supabase Auth and put the Google client ID/secret there, never in JavaScript. Configure the consent screen and test users if the app is in testing. Enable manual identity linking only if you want “Add Google sign-in” in account settings.
3. Set Supabase's Site URL to `https://cats.octov.uz` and allow these exact CatRank redirects:

```text
https://cats.octov.uz/auth/callback
https://cats.octov.uz/login?confirmed=1
https://cats.octov.uz/reset-password
https://cats.octov.uz/profile?email_confirmed=1
```

4. Set `GOOGLE_AUTH_ENABLED=true`, redeploy and test in the same browser tab. Test a new user and an existing email account. Do not delete or merge accounts to work around identity errors without verifying ownership.

Removing Google requires a working password and another linked email identity. Google-only accounts can use email password recovery first; keep Google connected until password sign-in works.

Provider reference: [Google sign-in with Supabase](https://supabase.com/docs/guides/auth/social-login/auth-google).

### Email

Enable email confirmation, **secure email change**, and the available security notifications in Supabase. Configure its Custom SMTP using the credentials and exact DNS records supplied by your provider, such as Resend. Follow `emails/README.md` to install the included templates. Flask does not need a Resend API key for this SMTP setup.

Test delivery, expiry, reused reset links, email-change confirmations, sender alignment and bounce handling. Configure Supabase's own auth rate limits and abuse protection as well as the Flask limits; direct Supabase Auth endpoints remain reachable. CAPTCHA and MFA are not implemented here.

### Phone — configure later, no code changes needed

Phone OTP endpoints and the login/registration forms are included. With `PHONE_AUTH_ENABLED=false`, visitors see only the configured sign-in methods and do not download the phone script.

When ready, configure a supported SMS provider inside Supabase Auth, enable the Phone provider, review SMS cost/region restrictions and provider-side limits, and test six-digit verification codes with a test account. Then set `PHONE_AUTH_ENABLED=true` in Vercel and redeploy. SMS provider credentials stay in Supabase, not browser code. Phone login does not automatically register a new user; registration is a separate choice. Optional profile contact text is not a verified login identity.

## What was kept and optimized

Kept: feed search/pagination, top-10 leaderboard, fixed navbar, fixed-height photo/comment viewer with outside arrows, expandable bio, scrolling comments, private favorites, uploader links, email/Google/optional phone auth, account settings, replies, comment likes, notifications, uploads, moderation and English/Russian text.

- Static URLs now use content fingerprints so changed CSS/JS is refreshed automatically after deployment.
- R2 initialization is deferred until an upload or managed-file deletion needs it, with bounded connection timeouts/retries.
- Phone code and its settings request are limited to enabled login/registration pages.
- Comment likes ignore stale account/viewer responses, block duplicate clicks before asynchronous work, load all paginated IDs in batches, and preserve optimistic updates.
- All comment edits use the database's server-clock two-minute window. Administrators retain moderation access; client-supplied timestamps/roles cannot bypass the window.
- The static build validates file types and paths, rejects hidden files/symlinks, and replaces only generated `public/static` so obsolete assets do not remain published.
- Only the used solid/regular Font Awesome fonts are included. The full-color Google SVG and all third-party licenses are kept.

Removed from this release: private `.env`, virtual environments, caches, Git history, generated public output, unused brand/legacy icon fonts, duplicate setup/roadmap documents, and Docker/Railway/Gunicorn launch files/dependency. The original upload remains unchanged. This edition targets Vercel; local `python app.py` remains available for development, not production hosting.

`tests/`, `migrations/`, `emails/`, and `licenses/` are intentional: they support verification, upgrades and license compliance. They are excluded from the Vercel upload where they are not needed at runtime. Visitors can access public `/static/` assets, not Python, environment, SQL, or template source through app routes.

## Development and verification

Use Python 3.12 in a fresh virtual environment. Install `requirements-dev.txt` for tests or `requirements.txt` for runtime only. Start locally with `python app.py`; keep development settings in a private `.env`.

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/test_interactions.cjs tests/test_account.cjs tests/test_comment_likes.cjs
npm --prefix tests install
node tests/test_database.cjs
python build_vercel.py
```

Node is needed only for development checks. The SQL suite uses an isolated PGlite database with built-in UUID support in place of pgcrypto. Tests replace external services and clear relevant environment settings; no live credentials are needed.

Automated release checks cover routes, source-file protection, ownership, upload validation, cache fallback, migration reruns, replies/cascades, like counts, edit deadlines, OAuth intent, private favorites, viewer navigation, script syntax, and referenced asset files. They do not replace testing real providers or deployed appearance. The preview browser could not access the local server during this build; live OAuth, email, SMS, R2, Redis, hosting and visual appearance were not verified.

### Before directing users to the new deployment

- Verify email signup/confirmation/login/logout/recovery and any enabled Google flow with test accounts.
- Upload/edit/delete a cat and avatar; check storage and rejected oversized/invalid images. On Vercel, the app allows 4 MiB per image plus bounded multipart overhead.
- Check votes, favorites privacy, comment replies/likes, editing before and after two minutes, deletion and account switching.
- Check desktop and phone layouts: fixed navbar, visible arrows/close button, stable photo height, expanded bio and comments scrolling.
- Verify `/livez` and `/healthz`. Confirm `/app.py`, `/.env`, `/.git/config` and a migration URL return 404. Review server/provider logs and rate limits.
- Keep the previous deployment available. Roll back the deployment if auth/storage/error rates regress; do not remove database columns/functions during rollback.
