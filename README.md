# CatRank

Python 3.12 · Flask · Supabase Auth/PostgreSQL · optional Cloudflare R2.

## Updating an existing installation

This is the complete project. Keep your existing private `.env` or hosting environment variables, replace the application files, and restart/redeploy. This viewer update does not require a database change.

The cat viewer has a fixed, viewport-fitting frame. Previous/next controls sit outside the panel (below it on narrow phones). The header and comment form remain visible while the image, bio, and comments scroll. Arrow keys navigate the cats on the current page. The leaderboard stays limited to ten cats.

## Deploy

1. Run `supabase_migration.sql` in your Supabase SQL editor. Run this updated migration even if the previous version is installed.
2. Set the variables in `.env.example` on your host. Use `APP_ENV=production`, a random `SECRET_KEY` of at least 32 characters, and your HTTPS origin as `PUBLIC_SITE_URL`. The service key stays on the server.
3. In Supabase Auth, enable email confirmation and secure email change. Set Site URL to your HTTPS origin and allow these redirect URLs:
   - `https://YOUR-DOMAIN/login?confirmed=1`
   - `https://YOUR-DOMAIN/reset-password`
   - `https://YOUR-DOMAIN/profile?email_confirmed=1`
4. Configure Supabase SMTP for production email delivery. Secure email change may require confirmation from both inboxes.
5. Deploy the Dockerfile, or install `requirements.txt` and run `gunicorn --config gunicorn.conf.py app:app`. The server binds to your host's `PORT`. Railway configuration is included.
6. Keep one worker with `memory://`. For additional workers/replicas set a shared Redis URL in `RATE_LIMIT_STORAGE_URI`. Set `TRUST_PROXY_HOPS` to the actual trusted proxy count (usually 1 on managed hosting).

R2 is optional. Leave all R2 credentials blank to use the Supabase buckets created by the migration. To use R2, create its bucket, enable a public domain, and set all R2 variables.

`/livez` checks the process. `/healthz` checks configuration and database connectivity; it does not test email delivery or storage writes.

Before launch, verify signup confirmation, sign-in, recovery, email-change confirmation, upload, vote, and deletion with your own test account. This package was tested with isolated services; your live Supabase/email/storage configuration and browser layout still require verification.

## Local development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Set `ENABLE_DEMO_DATA=true` only for local sample data. Production rejects demo mode. Frontend assets are prebuilt; Node is not needed to deploy.

Before starting locally, fill in your service variables and use `APP_ENV=development`, `PUBLIC_SITE_URL=http://localhost:5000`, and `TRUST_PROXY_HOPS=0`. Never publish your private `.env`.

## Checks

```sh
pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/test_interactions.cjs
```

To rebuild CSS: `npm --prefix assets ci && npm --prefix assets run build`.
