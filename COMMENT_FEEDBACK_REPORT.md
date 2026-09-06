# CatRank comment delivery and error UX

## Production root cause: confirmation pending

A fresh, read-only GET of the configured Supabase `/rest/v1/` OpenAPI schema returned HTTP 200. It exposes all 13 comment columns used by the application and `validate_comment_reply`, but **does not expose `insert_comment_once`**. The current Flask POST route unconditionally calls that RPC. Its definition is in `migrations/20260905_recheck.sql`, which was missing from the README deployment sequence.

This is a confirmed API compatibility problem and the leading explanation for persistent comment failures. It does **not** prove whether the SQL function is absent, its grants are missing, or PostgREST's schema cache is stale. No fresh production journal excerpt or authenticated production POST was available during this work. Consequently, the exact cause of the user's production failure remains unconfirmed pending the immediately reproduced request log.

The missing-RPC test reproduces a 503 for PostgREST `PGRST202`. This test is simulated, not a captured production response. There is no current evidence connecting the reported comment failure to `RemoteProtocolError`; old 503s have not been treated as evidence.

## Reviewed SQL for Supabase SQL Editor

Use the exact contents of [migrations/20260905_recheck.sql](migrations/20260905_recheck.sql) after checking the fresh production failure. No SQL was applied remotely.

The transaction only creates/replaces `public.insert_comment_once(jsonb)`, restricts execution to `service_role`, and reloads the PostgREST schema cache. It does not alter/drop tables or modify existing comments. It retains the existing account/cat advisory lock and 60-second content cooldown. Repeated UUIDs return the original creation time with `existing`, including after the cooldown; ownership/content mismatches are rejected. The old request payload remains accepted.

Read-only SQL checks before and after applying the migration:

```sql
SELECT to_regprocedure('public.insert_comment_once(jsonb)') AS comment_rpc;
SELECT p.proname, p.prosecdef,
       has_function_privilege('service_role', p.oid, 'EXECUTE') AS service_can_execute,
       has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_can_execute,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated_can_execute
FROM pg_proc p
WHERE p.oid = to_regprocedure('public.insert_comment_once(jsonb)');
```

Expected after application: function present, security definer true, service permission true, anon/authenticated false. Apply this function definition before deploying the changed application.

## Comment changes

- Frontend: retains the same same-origin `POST /api/cats/<id>/comments`, JSON content type and `Authorization: Bearer <session token>`. Adds a stable UUID `submission_id` retained for a manual retry of the same draft/account. Disables Send before the session lookup, keeps its size and spinner state, blocks duplicate calls, and limits the fetch/body read to 15 seconds.
- Success: renders the acknowledged comment directly without requiring another GET, updates the count, clears the draft/error, and restores Send. Existing comments, chronological order and reply grouping remain intact.
- Failure: retains draft/reply context and the modal, restores Send, and shows only a compact inline alert. Fixed EN/RU messages map 401, 403, 429, 503, network and unknown errors; API bodies/exceptions are not shown.
- Backend: derives a server comment UUID scoped to the authenticated account, cat, reply target, text and submission ID. Existing clients without `submission_id` still receive a generated UUID. On an uncertain transport failure, reads that exact UUID scoped to owner/cat; if present, returns success. If absent or reconciliation fails, returns 503. **The write is never retried automatically.**
- Reply ancestry validation, permissions and the `6 per minute; 60 per hour` limiter remain. Replay responses do not generate another notification; deterministic IDs for comment/reply notifications also prevent duplicate records when an uncertain replay is reconciled. Notification delivery remains best effort: a failed notification write is logged and does not change a successful comment into a failure.
- Diagnostics: failed comment responses log request ID, route template and status. Database stages log only exception class and an allowlisted PostgREST/SQLSTATE code, with no exception text, traceback, token, credential or comment payload.

## Read reliability

Selected read operations retry **once**, after 100 ms, for RemoteProtocolError, ConnectError, ReadError, httpx timeouts and connection reset/aborted exceptions. Coverage includes comment/cat/reply reads, canonical/profile reads and paginated favorite/liked-cat collections. Exhaustion follows existing failure handling. Tests reproduce recovery and exhausted 503s. No general retry wrapper surrounds a mutation, notification, authentication write or profile update.

## Error UX and placement

Inline alerts now cover comment/reply submission, inline comment editing, login/register validation, registration avatar validation, uploads, profile/avatar errors and email-settings validation. Existing password form messages stay inline, gain alert semantics and avoid raw exception output. User input survives failures.

The bottom toast implementation and bottom snackbar CSS are removed. Global notices share a compact white/slate/purple toast with icon, short title, message, close button, downward stacking (maximum two), duplicate-message suppression, motion reduction support and accessible status/alert roles. Normal notices dismiss after 4.5 seconds; errors after 6 seconds; hover/focus pauses dismissal.

Desktop: top-right, 20px from the top/right when unobstructed. Mobile: top-center with 12px side margins and safe-area-aware top spacing. Placement moves below navigation or the modal close button when needed to keep those controls reachable. Mobile modal notices start below the close-button row. Comments do not produce routine success toasts or a duplicate error toast. The modal layout was not redesigned.

## Verification

Final results:

| Exact command | Passed | Failed |
| --- | ---: | ---: |
| `venv/bin/python -m unittest discover -s tests` | 117 tests | 0 |
| `node tests/frontend_regressions.test.cjs` | 25 tests | 0 |
| `node tests/browser_comment_feedback.cjs` | 132 browser scenarios | 0 |
| `git diff --check` | clean | 0 |

The Python total includes 22 new delivery/reliability tests and 13 real PostgreSQL migration tests. Browser coverage: 320, 360, 375, 390, 412, 430, 1440 and 1536 pixels, each in EN and RU at 900px viewport height; 0 JavaScript errors and 0 horizontal overflows. See [machine-readable browser results](artifacts/comment-feedback/results.json).

The fresh local browser runtime log contained no matches for RemoteProtocolError, Traceback, HTTP 500/502/503 or comment/notification insert errors. Its API/auth responses are fixtures; this says nothing about production health. Initial sandbox runs failed because local sockets were prohibited; the same tests passed with local socket access. Browser development caught and corrected desktop close-button overlap. An initial form fixture also needed to be signed out to prevent the existing authenticated redirect.

VERIFIED locally: real PostgreSQL migration application/reapplication, 16 concurrent same-UUID submissions producing one row, replay after cooldown, ownership/content rejection, Flask route behavior, shipped modal/template/JS/CSS rendering and UI interactions.

MOCKED / SIMULATED: Supabase/auth responses, HTTPX failures, missing-RPC response, notification failures, browser API/auth/image responses, 401/403/429/503/network/unknown UI failures. Browser tests use the actual Flask-rendered cat modal, not simplified HTML, but do not post to the production database.

NOT VERIFIED: fresh production failure log, production authenticated comment/reply success after deployment, real mobile keyboard/device behavior, live Supabase transport recovery, and fresh post-deployment production notification/error logs. Nothing was pushed or deployed.

After deploying the reviewed migration/code, reproduce a normal comment and reply on `https://cats.octov.uz`, verify the network POST status/body and count, and inspect only the fresh journal interval:

```bash
sudo journalctl -u catrank --since "2 minutes ago" --no-pager
```

Check for `RemoteProtocolError`, `Traceback`, 500/502/503, comment-insert and notification-insert failures. The traceback/503 entries in local unit-test logs are expected injected failures; they are not production evidence. The local browser runtime log uses fixture configuration and is likewise not a production log.


## Screenshots

Actual shipped modal; fixture account, cat image and API responses:

- [320px Russian inline failure](artifacts/comment-feedback/inline-320-ru.png)
- [390px English inline failure](artifacts/comment-feedback/inline-390-en.png)
- [390px English top toast](artifacts/comment-feedback/toast-390-en.png)
- [1440px English inline failure](artifacts/comment-feedback/inline-1440-en.png)
- [1440px English top toast](artifacts/comment-feedback/toast-1440-en.png)
- [1536px Russian top toast](artifacts/comment-feedback/toast-1536-ru.png)

## Every changed/added file

- [COMMENT_FEEDBACK_REPORT.md](COMMENT_FEEDBACK_REPORT.md)
- [README.md](README.md)
- [app.py](app.py)
- [artifacts/comment-feedback/inline-1440-en.png](artifacts/comment-feedback/inline-1440-en.png)
- [artifacts/comment-feedback/inline-1440-ru.png](artifacts/comment-feedback/inline-1440-ru.png)
- [artifacts/comment-feedback/inline-1536-en.png](artifacts/comment-feedback/inline-1536-en.png)
- [artifacts/comment-feedback/inline-1536-ru.png](artifacts/comment-feedback/inline-1536-ru.png)
- [artifacts/comment-feedback/inline-320-en.png](artifacts/comment-feedback/inline-320-en.png)
- [artifacts/comment-feedback/inline-320-ru.png](artifacts/comment-feedback/inline-320-ru.png)
- [artifacts/comment-feedback/inline-390-en.png](artifacts/comment-feedback/inline-390-en.png)
- [artifacts/comment-feedback/inline-390-ru.png](artifacts/comment-feedback/inline-390-ru.png)
- [artifacts/comment-feedback/results.json](artifacts/comment-feedback/results.json)
- [artifacts/comment-feedback/toast-1440-en.png](artifacts/comment-feedback/toast-1440-en.png)
- [artifacts/comment-feedback/toast-1440-ru.png](artifacts/comment-feedback/toast-1440-ru.png)
- [artifacts/comment-feedback/toast-1536-en.png](artifacts/comment-feedback/toast-1536-en.png)
- [artifacts/comment-feedback/toast-1536-ru.png](artifacts/comment-feedback/toast-1536-ru.png)
- [artifacts/comment-feedback/toast-320-en.png](artifacts/comment-feedback/toast-320-en.png)
- [artifacts/comment-feedback/toast-320-ru.png](artifacts/comment-feedback/toast-320-ru.png)
- [artifacts/comment-feedback/toast-390-en.png](artifacts/comment-feedback/toast-390-en.png)
- [artifacts/comment-feedback/toast-390-ru.png](artifacts/comment-feedback/toast-390-ru.png)
- [migrations/20260905_recheck.sql](migrations/20260905_recheck.sql)
- [static/css/style.css](static/css/style.css)
- [static/js/account.js](static/js/account.js)
- [static/js/auth.js](static/js/auth.js)
- [static/js/main.js](static/js/main.js)
- [static/js/toast.js](static/js/toast.js)
- [static/js/upload.js](static/js/upload.js)
- [templates/base.html](templates/base.html)
- [templates/forgot_password.html](templates/forgot_password.html)
- [templates/profile.html](templates/profile.html)
- [templates/register.html](templates/register.html)
- [templates/reset_password.html](templates/reset_password.html)
- [templates/set_password.html](templates/set_password.html)
- [tests/browser_comment_feedback.cjs](tests/browser_comment_feedback.cjs)
- [tests/frontend_regressions.test.cjs](tests/frontend_regressions.test.cjs)
- [tests/test_comment_delivery.py](tests/test_comment_delivery.py)
- [tests/test_migrations.py](tests/test_migrations.py)

Generated local-only log (ignored by Git): `artifacts/comment-feedback/runtime.log`. Raw test logs are under `/tmp/catrank-*.log`; they are not release assets.
