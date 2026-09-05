# Production readiness review — 2026-09-05

## Release decision

Code and deployment fixes are implemented with regression coverage. Production
release still requires **credential rotation, database migration reconciliation,
and staging verification**. No live Supabase schema, storage policy, provider
configuration, or deployed site was modified or certified by this review.

## Critical findings and fixes

| Severity | Finding | Resolution / evidence |
| --- | --- | --- |
| Critical — release blocker | Current local signing key, Supabase service key, and R2 access/secret keys appear in Git history. | Exact-value comparison against all 40 existing local commits found matches, including `db6ba4469877` and `2b9ee7db9623`. Current tracked files had no matching credentials. Rotate/revoke the exposed credentials; update local and hosted environments. Values are deliberately omitted here. |
| High | Static validation skipped hidden paths while the copy operation published them. A nested `.env` or `.git` directory could reach the CDN. | Publishing now excludes every hidden entry, rejects symlinks and special files, stages output, and restores the previous build on replacement failure. Ten regression tests cover these cases. |
| High | The repository contained incremental migrations but no base tables or `toggle_cat_like()` implementation. Fresh deployment could not initialize. | Added a Supabase baseline with tables, foreign keys, restricted grants/RLS, profile/storage setup, and a row-locked vote function. Local PostgreSQL tests cover initialization, repeat migration application, concurrent votes, and deletion cascades. Existing schemas require comparison before applying the baseline. |
| High | Re-submitting stale login `app_metadata` could restore an administrator role after a concurrent demotion. | Password capability updates send only their own metadata key; server authorization remains based on trusted claims or confirmed allowlisted emails. User-editable roles never grant access. |
| High | Account-wide identity timestamps could let a newer matching Google login make an older mismatched identity appear acceptable. | OAuth authorization rejects an account while any attached Google identity has a different email. Password login retains the existing stale-identity release flow. |
| High | Separate production workers could enforce independent memory rate limits, including after Redis failure. | Production now requires shared Redis and disables local fallback. Vercel production detection, generated-secret validation, public-key checks, trusted hosts, and health checks prevent common misconfiguration. |
| High | Responses started under one account could repopulate private notification/vote state after logout or account switching. | Account generations discard stale responses, clear private caches, and isolate pending mutations. Contact/moderation pages hide and reload on account changes, including cross-tab logout. |
| Medium | Admin pagination raised uncaught conversion errors; raw OR-search interpolation allowed PostgREST filter grammar to alter the intended search. | Pagination is validated and bounded, searches are length limited and quoted, LIKE `%`/`_` are escaped, and query failures return sanitized 503s. PostgREST's documented `*` search wildcard is retained. This was filter-expression injection, not arbitrary SQL execution. |
| Medium | Admin totals summed only one PostgREST result page and could return false zero/success results during outages. User rows displayed placeholder zero counts. | Aggregate RPCs return exact overall totals and batch counts for a page of users. Failure returns 503. Tests include more than 1,000 cats and users with no cats. |
| Medium | Public-profile cache invalidation deleted a different key from the one being read. Failed cat lookups could cache an empty successful profile. | Per-user cache generations invalidate actual reads; failed cat queries return 503. Phone-only fallback names no longer reveal phone suffixes. |
| Medium | Request-local Auth clients left HTTP connections open. Oversized uploads caught HTTP exceptions and could become 500s. | Auth clients close in `finally` without revoking returned login sessions. Temporary proof/security sessions are locally revoked. Uploads preserve 413, reject additional malformed-image errors, and bound multipart resources. |
| Medium | Duplicate-signup provider exceptions returned an account-existence signal despite the generic success path. | Duplicate exceptions return the same confirmation response. Supabase email confirmation must stay enabled. |

## Performance changes

- Admin overview now makes one database RPC and transfers one row, replacing three
  queries and an application-side sum over potentially truncated cat records.
- Admin user counts use one batch RPC for the entire page, avoiding per-user queries.
- Added feed, ranking, user-cat, and notification indexes for the actual filter/order
  combinations. Existing indexes must be checked during migration reconciliation.
- Browser notification/vote snapshot requests coalesce. Comment-like state fetches
  batches of at most 100 and only requests unknown IDs instead of ignoring later pages.
- Comment edit controls use a map instead of repeatedly scanning the loaded comments:
  O(n + m) for n comments and m controls, replacing O(n × m).
- Supabase database/storage operations have explicit 10-second operation timeouts;
  R2 uses bounded connection/read timeouts and two total attempts. These are per
  operation bounds, not a guarantee that a multi-call route finishes in 30 seconds.
- Static-image resizing/WebP conversion, image/frame budgets, cache TTLs, and
  fingerprinted asset references remain in place. Invalid upload selections now
  clear preview resources.

Representative implemented database aggregation:

```sql
SELECT count(*), COALESCE(sum(c.likes_count), 0)::bigint,
       (SELECT count(*) FROM public.profiles),
       (SELECT count(*) FROM public.comments)
FROM public.cats c;
```

Representative implemented browser lookup:

```javascript
const commentsById = new Map(loadedComments.map(comment => [String(comment.id), comment]));
document.querySelectorAll('[data-edit-comment-id]').forEach(button => {
    const comment = commentsById.get(String(button.dataset.editCommentId));
    if (!comment) return;
    // Apply the edit-window state to this control.
});
```

These are structural improvements; no production latency or load-capacity claims
are made without measurements against the deployed services.

## Security and deployment posture

`.gitignore` and `.vercelignore` protect environment files, common credential/key
files, databases, logs, and build/tool artifacts. Secret matching used the local
configured credential values without printing them. It does not prove that every
historical or unknown secret has been found. Rotate credentials first, inspect
provider access logs, and coordinate any later history cleanup with repository
owners; rewriting Git history does not revoke credentials.

The browser/API remain same-origin. Cross-origin access is not enabled; bearer
credentials are required for protected API actions. Existing CSP, nosniff,
frame restrictions, production HSTS, and no-store API headers are retained.
Host rejection now avoids rendering templates before Flask has a URL adapter.

Dependencies are fully pinned, including four previously implicit transitive
packages. The CI template uses immutable GitHub Action revisions, read-only repository
permissions, Python 3.12, backend/browser regression tests, syntax/build checks,
and dependency auditing. It is inactive because GitHub rejected the initial push
for missing token `workflow` scope; activation instructions are in README. A Git
push may still trigger other repository-configured automation;
required environment values and SQL functions must be installed before release.

## Verification evidence

- Backend/unit and disposable PostgreSQL integration suite: **52 tests passed**,
  including nine PostgreSQL tests. Tests never load `.env` or contact live Supabase.
- Browser regression tests: **13 tests passed**, using Node's test runner and simulated DOM/network timing.
  They cover stale account responses, pending mutations, batching, duplicate clicks,
  private-page resets, and notification unread-count races.
- Runtime `pip check`: no broken requirements.
- `pip-audit` 2.10.1 online PyPI audit: **53 packages, zero known vulnerabilities**
  reported on 2026-09-05. This is advisory coverage at audit time, not a guarantee.
- Python 3.12 dependency resolution succeeded for all 53 packages; selected binary
  wheels include CPython 3.12 wheels. Execution locally used Python 3.14.6 and
  PostgreSQL 18.6; the inactive CI template targets Python 3.12.
- Python 3.12 grammar checks passed. Syntax checks passed for 11 browser scripts
  and 56 inline scripts rendered across 12 page routes. Static publishing produced
  21 public files. Whitespace checks and current-tree secret checks passed.

## Remaining operational and scale limits

1. Rotate the exposed service/storage/signing credentials and confirm the old
   credentials no longer work. For legacy Supabase service-role JWTs, follow the
   provider's rotation procedure and account for effects on related JWT keys/sessions.
2. Reconcile the live schema/triggers, apply required migrations, configure Redis,
   validate trusted proxy hops and hostnames, and run the staging journeys in README.
   Database backups, restore testing, alerts, storage permissions, OAuth redirects,
   email delivery, and live provider behavior were not exercised here.
3. Several profile/ID-list routes still fetch up to 10,000 rows in 500-row batches;
   very large accounts can have truncated lists/statistics and high request cost.
   Replace these contracts with cursor pagination and aggregates before supporting
   accounts at that scale. Account deletion still cleans objects synchronously;
   large deletions or provider failures need a durable cleanup queue/reconciler.
4. CSP still permits inline scripts for the existing inline handlers/templates.
   A nonce-based policy requires migrating those handlers. Dynamic values reviewed
   here use escaping/safe URL handling, but a full browser penetration test was not run.
5. Duplicate-comment suppression uses a check before insert and can race under
   simultaneous requests. Rate limits bound traffic; strict deduplication would
   require a database lock or an idempotency-key contract.

Implementation choices were checked against the primary documentation for
[Flask resource and host security](https://flask.palletsprojects.com/en/stable/web-security/),
[Flask-Limiter storage behavior](https://flask-limiter.readthedocs.io/en/stable/configuration.html),
and [PostgREST quoted filter values](https://docs.postgrest.org/en/v13/references/api/url_grammar.html).
