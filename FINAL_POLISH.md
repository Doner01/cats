# Final production polish — September 5, 2026

## Scope and architecture

This pass builds on the current working tree. Flask, Gunicorn, Nginx, the Oracle
Ubuntu VPS, Supabase Auth/PostgreSQL, R2, Redis, and Cloudflare remain in place.
No runtime dependencies, database migrations, Workers, tracking, or new services
were added. Production credentials and `.env` were not read or changed. The
pre-existing, untracked `test_comments.py` was left untouched; it imports the real
environment and was deliberately not executed.

## Improvements and exact defects fixed

- Added `/contact` with configurable Telegram, Discord and email cards, accessible
  links, responsive layout, unavailable states, and a footer link on every page.
- Added optional SMTP contact delivery with real submission confirmation and
  useful validation/failure messages. Disabled or incomplete configuration leaves
  the page usable and clearly marks the form unavailable.
- Comments had no request deadline. A connection that never returned headers or
  finished its response body could leave “Loading comments...” indefinitely.
  Comment reads now abort after 15 seconds and show a retry button. A current
  aborted request also shows retry; obsolete responses still cannot overwrite
  another cat. Repeated failures replace their retry button rather than adding
  duplicates. Existing comment rendering and pagination are preserved.
- Closing a cat modal previously left its initial network requests running until
  completion or a later modal open. Closing now aborts those requests.
- A pending comment submission could leave the next cat's Send button disabled,
  and its completion could reset a newer submission's button. Opening a modal
  now resets the composer; completions update it only for the originating modal
  version. The submit handler also checks the disabled state.
- At 320–430px, the homepage search control's minimum size pushed the sort control
  outside the viewport (measured document width up to 436px). The search flex item
  can now shrink; the sort control stays accessible in the same row.
- The Account & Security dialog relied on `max-h-[92dvh]`, absent from the compiled
  Tailwind stylesheet. Explicit viewport height limits and internal scrolling now
  keep it on screen, including short viewports.
- Long account emails overflowed Google sign-in help. Security text and profile
  email/bio now wrap within their available width. Settings tab padding fits 320px.
- Comment Edit buttons lost their accessible name when their text was hidden by
  CSS; explicit edit/delete labels now survive that styling. Profile settings has
  an explicitly labeled close button.
- HTML 429, Redis-outage 503 and oversized-request 413 responses were plain text.
  They now use the CatRank error design. 403/404/500/503 have appropriate headings,
  support navigation, and server errors include a request reference, not details.
- Added canonical URLs for public landing pages, Open Graph/Twitter text metadata,
  private/error-page noindex tags, robots.txt and a three-page public sitemap.
  Existing favicon remains. No private profile/API/auth routes enter the sitemap.

## Contact configuration

All values live in the server environment; safe, empty examples are in `.env.example`.
Set real values only on the server. Restart Gunicorn after changing them.

| Variable | Default / purpose |
| --- | --- |
| `TELEGRAM_URL` | Empty; your real HTTPS Telegram channel/community URL |
| `DISCORD_URL` | Empty; your real HTTPS Discord invitation/community URL |
| `CONTACT_EMAIL` | Empty; public support mailbox and fixed delivery recipient |
| `CONTACT_EMAIL_ENABLED` | `false`; explicitly enables optional sending |
| `CONTACT_SMTP_HOST` | Empty; provider SMTP hostname |
| `CONTACT_SMTP_PORT` | `587` |
| `CONTACT_SMTP_USERNAME` | Empty; provider login, if required |
| `CONTACT_SMTP_PASSWORD` | Empty; provider password; server only |
| `CONTACT_SMTP_FROM` | Falls back to `CONTACT_EMAIL`; use a provider-authorized sender |
| `CONTACT_SMTP_USE_TLS` | `true`; verified STARTTLS |
| `CONTACT_SMTP_USE_SSL` | `false`; for implicit TLS, use port 465, SSL=true, TLS=false |
| `PUBLIC_SITE_URL` | Existing setting; clean canonical HTTPS origin, required in production |

The form also needs existing Redis configuration: `RATE_LIMIT_STORAGE_URI` for
Flask-Limiter, and `CACHE_REDIS_URL` (falls back to the limiter URI) for shared
submission claims. With no Redis client configured, sending is unavailable.
Keep both services private and preserve the existing Nginx real-IP configuration
and `TRUST_PROXY_HOPS` value appropriate to it.

Missing/invalid public links are unavailable cards, never fake links. The form
accepts Name (80), Email (254), Subject (120), Message (5000 characters), and rejects
oversized requests. Email supports a single conventional ASCII mailbox.

A signed, session-bound form token expires after one hour. A hidden spam trap and
minimum two-second form age supplement limits of two submissions/minute and five
/hour per visitor IP. Redis `SET NX` claims prevent duplicate sends across workers.
Failures of Redis stop sending; SMTP errors never produce a success message.
Message bodies are plain text, templates escape input, header controls are rejected,
and only the configured mailbox can receive messages. Visitor email is Reply-To,
not From. TLS certificate verification is mandatory. SMTP socket timeout is ten
seconds per operation. SMTP acceptance is reported accurately; inbox delivery is
not guaranteed by an SMTP acknowledgement.

Provider configuration is manual: supply credentials and the authorized sender,
configure any sender/domain verification the provider requires, and test delivery
and Reply-To from the production host. No actual email was sent during this pass.

## Performance and cache safety

Database queries, batching/concurrency, Redis feed/profile/leaderboard caching,
indexes, image processing, storage and notifications batching are preserved.
No speculative database/query refactors were made; no production latency
improvement is claimed. The new contact route does not query Supabase. Its small
script is loaded only on that page. Normal pages do not create a contact session.
Aborting closed-modal requests reduces unnecessary browser work.

Existing `asset_fingerprint()` already hashes content (SHA-256, first 12 characters),
and script/styles use `?v=<hash>`. New contact JavaScript uses the same mechanism.
Fingerprints are cached per worker; restart all Gunicorn workers with each release.
Static responses retain `public, max-age=86400`; HTML and APIs remain `no-store`.
Cloudflare must include the query string in the static cache key. If a custom
Cloudflare rule ignores query strings, correct that rule or purge affected assets
once during release. Keep `/static/*` caching enabled; do not add HTML/API caching.

## Security review

Reviewed bearer authentication, admin authorization, cat/comment ownership,
notification user filters, favorite ownership, signed comment cursors, upload
byte/format/dimension limits, storage path construction, escaping/URL handling,
public-key configuration guards, safe auth redirect destinations, proxy trust and
rate limiting. Existing tests exercise invalid/mismatched Google identities,
service-role key rejection, authorization failures and backend-only SQL privileges.
No additional confirmed authorization or storage defect was found in this pass.
New contact handling has dedicated CSRF, injection, failure and spoofed-header tests.
Existing Bearer-auth API guards and CSP were not weakened.

## Verification

- Python: `venv/bin/python -m unittest discover -s tests` — **88 passed**, including
  all existing migrations against a disposable local PostgreSQL and 17 new
  contact/public-page checks. Expected simulated failure logs contain test data.
- JavaScript: `node tests/frontend_regressions.test.cjs` — **24 passed**. Seven new
  regressions cover stalled headers, stalled bodies, current aborts, stale aborts,
  late stale response bodies, and submission guards across modal changes. Existing tests cover account changes, likes,
  favorites, notification deduplication and batched comment likes.
- Browser: `tests/browser_polish.cjs` uses Chromium and a local fixture server,
  never the deployed database, Auth provider, R2 or SMTP. **243 page/viewport combinations passed**, with no page-level horizontal overflow
  or uncaught JavaScript errors. Console review found only the deliberately exercised
  HTTP error responses; no unexpected console errors. All requested widths:
  **320, 360, 375, 390, 412, 430, 768, 1024, 1440px**. Includes page layouts,
  Account & Security, email settings, notifications, cat modal, and a 320×420
  keyboard-height simulation. Browser output and screenshots go to
  `/tmp/catrank-browser-results` by default.
- Contact browser submission checks real Flask validation/redirect/rendering with
  a mocked mail transport. Backend tests verify STARTTLS, implicit TLS, headers,
  no credential exposure, unavailable configuration, expiry/CSRF, max lengths,
  control/header injection, escaping, duplicate claims, SMTP failure, Redis
  failure and IP rate limiting despite spoofed forwarding headers.
- Browser interactions also cover registration confirmation, login/logout, Google
  sign-in initiation, password-reset requests, upload submission, loaded images,
  cat likes and favorites using fixtures.
- Browser comments use fixture API responses for zero/existing comments, add,
  reply, edit, delete, like, pagination, retry, close/reopen, rapid A→B switching,
  and a real 15-second stalled-request timeout.
- Syntax: Python compilation, 77 inline/static JavaScript scripts checked with
  `node --check`,
  Jinja template compilation, and `git diff --check`.

Run the optional browser harness without adding project/runtime dependencies:

```bash
npm install --prefix /tmp/catrank-browser-check --cache /tmp/catrank-npm-cache --no-audit --no-fund @playwright/test
PLAYWRIGHT_BROWSERS_PATH=/tmp/catrank-browsers /tmp/catrank-browser-check/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/catrank-browser-check/node_modules PLAYWRIGHT_BROWSERS_PATH=/tmp/catrank-browsers node tests/browser_polish.cjs
```

The harness uses port 5099 and the repository's `venv/bin/python`. PostgreSQL and
Chromium need normal local process/socket permissions; the restricted tool sandbox
blocked these, so checks were rerun with the required execution permission.

## Production commands and manual release checks

Deploy these reviewed files using your existing deployment process. No pip install,
new mail dependency, database migration, Nginx reload or Cloudflare architecture
change is required for this pass. These are examples: replace the directory,
service name and origin with the values from your existing deployment.

```bash
cd /path/to/your/current/catrank
venv/bin/python -m compileall -q app.py contact.py
# Set the desired contact variables in the existing server-only environment.
# Use the actual systemd unit that runs your Gunicorn app:
sudo systemctl restart catrank
sudo systemctl status catrank --no-pager
CATRANK_ORIGIN='https://your-real-domain'
curl -fsS "$CATRANK_ORIGIN/livez"
curl -fsS "$CATRANK_ORIGIN/healthz"
curl -fsS -o /dev/null "$CATRANK_ORIGIN/contact"
curl -fsS "$CATRANK_ORIGIN/robots.txt"
curl -fsS "$CATRANK_ORIGIN/sitemap.xml"
curl -I "$CATRANK_ORIGIN/"
```

Verify a new page's JS/CSS URLs contain the current hashes and that Cloudflare's
cache key includes `v`. Test actual Telegram/Discord destinations, one contact
submission and Reply-To delivery, login/logout, Google callback, recovery emails,
upload to R2 and comments using a test account. Existing migrations were tested
locally, not applied to production by this pass.

## Limits of verification

No live deployment, production credentials, Supabase project, real Google account,
SMTP inbox, Redis server, Cloudflare cache rules, TLS settings or Nginx configuration
was accessed. Redis rate-limit behavior was exercised using Flask-Limiter's isolated
memory test storage; Redis claims/outages used mocks. Cross-worker behavior follows
the existing configured Redis limiter and atomic SET NX, but was not tested against
a running Redis instance. Browser Auth/API calls use fixtures, so successful real
registration, password/recovery, R2 writes and email delivery still need staging or
production smoke checks. PostgreSQL fixtures emulate Supabase auth/storage schemas;
they do not constitute a production schema audit. Physical iOS/Android keyboards,
Safari, Firefox, screen readers and real network/edge performance were not tested.
The browser checks test viewport dimensions and keyboard interaction, not a complete
accessibility or penetration audit.

## Files changed or added

- `.env.example` — public community and optional SMTP settings; canonical origin example.
- `app.py` — contact registration, branded errors, metadata context, robots and sitemap.
- `contact.py` — new optional secure contact delivery module.
- `templates/contact.html` — new community/support page and form.
- `templates/base.html` — metadata and footer discovery link.
- `templates/error.html` — status-specific headings and support navigation.
- `templates/profile.html` — accessible settings close control.
- `static/css/style.css` — contact styling, mobile feed and settings fixes, safe wrapping.
- `static/js/contact.js` — new submit progress/double-submit behavior.
- `static/js/main.js` — bounded comment reads, cancellation, submit-state and labels.
- `static/js/translations.js` — English/Russian contact footer label.
- `tests/test_contact.py` — contact, metadata, cache and route regression tests.
- `tests/frontend_regressions.test.cjs` — comment lifecycle regressions.
- `tests/browser_server.py` — isolated Flask browser fixture server.
- `tests/browser_polish.cjs` — repeatable Chromium responsive and interaction harness.
- `README.md` — current VPS architecture and link to this report.
- `FINAL_POLISH.md` — this release/configuration/verification record.
