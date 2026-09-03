# CatRank Final v1.0

Clean final-project build of CatRank.

## Runtime stack
- Flask / Python
- Supabase Auth + PostgreSQL
- Cloudflare R2 image storage
- Optional Redis cache / shared rate limiting
- Vercel deployment

## Required project files
Keep `app.py`, `templates/`, `static/`, `migrations/`, `emails/`, `licenses/`, `requirements.txt`, `build_vercel.py`, `vercel.json`, `.python-version`, `.gitignore`, and `.vercelignore`.

## Local secrets
Keep `.env` only on your own computer. Do not commit it. Production secrets belong in the hosting provider's environment variables.

## Supabase auth settings
Enable the authentication providers you use, email confirmation, secure email change, and secure password change. Google OAuth uses `/auth/callback`. CatRank V4.4 also requires **Allow manual linking** so stale Google identities can be safely released after an email change.

## Deployment
Vercel uses `python build_vercel.py` from `vercel.json`. Install runtime dependencies from `requirements.txt`.

After deployment, test login/register, Google sign-in, email change, password change/reset, avatar upload, cat upload, comments, favorites, notifications, and sign-out with test accounts.
