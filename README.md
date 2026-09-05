# CatRank

Flask application with Supabase Auth/PostgreSQL, Cloudflare R2 or Supabase Storage,
Redis rate limiting/cache, and Vercel deployment. Python 3.12 is the deployment
runtime; see `.python-version`.

## Release requirements

Read [PRODUCTION_REVIEW.md](PRODUCTION_REVIEW.md) before deploying. The review
found credentials from the local environment in Git history. Rotate the exposed
Supabase service credential, R2 credentials, and Flask signing key before release.
Ignoring `.env` does not invalidate credentials already committed in older revisions.

## Development

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Set your development project's environment values in .env.
.venv/bin/python app.py
```

The Flask development server is for local use. Vercel imports `app` from `app.py`.
Never commit `.env`, credentials, or database dumps. Production values belong in
the hosting provider's environment settings.

## Database and storage

For a **new Supabase project**, apply these SQL files in order in its SQL editor:

1. `migrations/20260901_base.sql`
2. `migrations/20260902_phone_comments.sql`
3. `migrations/20260902_favorites.sql`
4. `migrations/20260902_roadmap.sql`
5. `migrations/20260905_production_hardening.sql`

The base migration creates application tables, foreign keys, protected backend
functions, profile triggers, and public image buckets. Supabase must already
provide the `auth` and `storage` schemas and its standard roles. Browser clients
cannot read/write application tables directly; Flask performs those operations
after checking authorization. The public/anon key is intended for browser Auth;
the service key must remain exclusively on the backend.

For an **existing project**, back up the database and compare its schema and
triggers against the baseline. `CREATE TABLE IF NOT EXISTS` does not reconcile
an older schema. Do not blindly install a second vote-count/profile trigger on
top of a historical trigger. Apply missing migrations and install the final
production-hardening migration **before releasing the updated app**: admin pages
require `admin_overview_counts()` and `admin_user_counts(uuid[])`.

R2 is optional. Configure all four R2 credential/domain variables together, or
leave all four empty to use Supabase Storage. The application re-encodes static
images as WebP and preserves validated animated GIFs. Keep storage write access
restricted to the backend; public bucket URLs supply image reads.

## Authentication settings

Enable email confirmation, secure email change, and secure password change in
Supabase. Enable Google only when configured and set `GOOGLE_AUTH_ENABLED=true`.
Manual identity linking must be enabled for the existing email-change flow to
release stale Google identities. Phone sign-in is configured in Supabase; there
is no backend `PHONE_AUTH_ENABLED` environment switch.

Set Supabase's Site URL to the canonical `PUBLIC_SITE_URL` and allow the required
redirect URLs under that origin: `/auth/callback`, `/login`, `/reset-password`,
and `/profile`. Use an explicit preview origin when testing previews.

Admin access trusts server-controlled `app_metadata.role=admin` or a verified
email in `ADMIN_EMAILS`. User-editable metadata and the profile role shown in the
admin list do not grant backend privileges.

## Vercel configuration

Install dependencies from `requirements.txt`. `vercel.json` uses
`python build_vercel.py` to publish only approved static assets to `public/static`.

Set `APP_ENV=production`, `PUBLIC_SITE_URL` to a clean HTTPS origin, a freshly
generated `SECRET_KEY` of at least 32 characters, and all three Supabase values.
Vercel's `VERCEL_ENV=production` also enables production validation. The example
signing key, privileged keys in the browser key slot, demo data, and debug mode
are rejected in production.

Set `RATE_LIMIT_STORAGE_URI` to shared `redis://` or preferably `rediss://` Redis.
An in-memory fallback is disabled in production so separate workers cannot
bypass account/IP limits. Redis outages return a temporary-unavailable response
for limited requests. Optional application caching uses the same endpoint unless
`CACHE_REDIS_URL` is set. Cache failures allow database reads to continue.

`TRUSTED_HOSTS` may explicitly list hostnames, comma separated. Otherwise the
canonical hostname and Vercel deployment hostnames are trusted automatically.
Configure `TRUST_PROXY_HOPS` only after verifying the exact trusted proxy chain;
test that different clients have different rate-limit IP keys and cannot spoof
forwarded headers. Country restrictions require Vercel's trusted geo header and
an explicit `ALLOWED_COUNTRIES` list.

The browser and API use the same origin, so cross-origin CORS access is not
enabled. A separate frontend requires an explicit origin allowlist and review of
credential handling before changing that policy.

`/livez` checks process liveness without remote calls. `/healthz` checks the database
and, in production, shared rate-limit storage. It returns 503 when unavailable.

## Verification

```bash
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
node tests/frontend_regressions.test.cjs
find static/js -name '*.js' -print0 | xargs -0 -n1 node --check
.venv/bin/python build_vercel.py
```

The database tests use a disposable local PostgreSQL cluster, never `.env` or a
configured Supabase database. Install PostgreSQL server tools and put their bin
directory on `PATH` to run them; otherwise they explicitly skip.

The inactive CI template is `.github/production-checks.yml.example`. It runs these
checks on Python 3.12 and audits pinned dependencies with `pip-audit`. GitHub
rejected installation of an active workflow because the current push token lacks
`workflow` scope. To enable CI, use a credential authorized to manage workflows,
move the template to `.github/workflows/ci.yml`, then commit and push it.

Before serving production traffic, verify health checks and exercise registration,
login, password reset, Google sign-in, email/password change, image uploads, voting,
comments, favorites, notifications, moderation, and sign-out with staging accounts.
