# Security scan remediation

Source: `codex-security-license-service-gTPBEt/report.md`, revision
`0c2348a16552baf9c0e2a36cc499beb8bd652119`. Numbers below follow the report's table,
not the ordering of `findings.json`. The original scan was static; these repairs
add executable adversarial and integration coverage.

| # | Finding | Repair | Regression evidence |
| --- | --- | --- | --- |
| 1 | Unbounded registration | Durable hourly peer/global attempt limits before hashing; serialized registration hashes; total account capacity | Shared JSON/HTML limits, no hashing after rejection/capacity, concurrent registration |
| 2 | Unlimited password guesses | Shared persistent account/source lockouts in the Django backend for API, HTML and Admin | `test_login_throttling.py`, including distributed sources and SQLite contention |
| 3 | Oversized names and unbounded device history | Central 200-character name validation, database constraint, bounded oldest-unbound pruning under entitlement lock | Every bind/rename adapter, direct database write, repeated unbind/rebind |
| 4 | HTTP session disclosure | Production Secure cookies, HTTPS redirects, HSTS; proxy scheme trust is explicit | Real WSGI HTTP redirect and login Set-Cookie test |
| 5 | Case-variant identity race | Database `LOWER(username)` unique index, transactional registration, 409 on duplicate | Concurrent `Alice`/`alice` requests; direct duplicate insert; migration refuses existing collisions |
| 6 | Passwordless inactive sessions | Only backend-authenticated active users reach login; activation changes invalidate sessions; upgrade retires all old sessions | API/HTML/Admin inactive login; replay after reactivation; migration session purge |
| 7 | Request-ID audit injection | Bounded URL-safe request IDs and JSON-encoded audit records | Spaces, line breaks, nulls, commas and overlong IDs cannot forge fields |
| 8 | Plaintext keys in sessions/backups | Immediate non-cacheable POST delivery for batch and single Admin issuance; no message/session handoff | Issuing responses, decoded database sessions, cookies and subsequent GETs inspected |
| 9 | Missing HTML/Admin audit | Shared JSON audit emission and middleware with actor, outcome and known resource IDs; Admin hooks cover model mutations | Successful and failed customer mutations and Admin status changes |
| 10 | Revocation/suspension race | Recheck current entitlement under row lock; anonymous activation locks key then entitlement and rechecks both | Stale resolution tests plus PostgreSQL concurrent revocation commit ordering |
| 11 | Debug disclosure and parser failures | Debug defaults off; missing production secret fails WSGI import; explicit loopback debug setting; body, Unicode and JSON validation; sanitized expected DB errors | WSGI/default configuration tests, real HTTP malformed input, surrogate/nesting/size regressions |
| 12 | Empty-body session CSRF | Content type checked before empty-body shortcut; supplied Origin must match exactly for session/auth writes | All no-field session/admin mutations reject form media types without changes; sibling JSON origin rejected |
| 13 | Login timing enumeration | Missing, inactive and active wrong-password attempts all pass through backend hasher work | Equal configured-hasher invocation counts for all three paths |

## Upgrade behavior

- Configure the production secret, allowed hosts and TLS edge before starting.
- Run migrations. Existing sessions are invalidated once by `0004`; account data
  is retained. Duplicate identities stop migration rather than being merged.
- Existing oversized device names must be corrected before the new constraint.
- Database `LOWER` defines identity equivalence: SQLite's built-in case folding is
  ASCII-only, while PostgreSQL follows its database locale.
- Historical unbound device rows beyond the budget are pruned on the next new
  binding. Active bindings are retained, with a budget no smaller than the seat count.
- Admin issuance is a direct POST response. Resubmitting that POST issues another
  batch; subsequent GETs do not recover the original plaintext.
- Earlier backups cannot be repaired by this code and may contain old key-delivery
  sessions. Backup retirement remains an operator task.

## Validation results

- SQLite: **127 passed, 2 skipped** (PostgreSQL-only lock-order tests).
- PostgreSQL 17: **128 passed, 1 skipped** (SQLite-only lock-retry test), with
  `psycopg[binary]==3.2.13` installed in the temporary test environment.
- Both suites include migration upgrade checks and real WSGI HTTP cookie/redirect checks.
- Ruff lint/format checks, Django system checks, migration drift check, and
  `git diff --check` pass.
- Both suites report three existing `django-unfold` deprecation warnings.

## Verification scope

The tests exercise SQLite and a disposable local PostgreSQL 17 instance, including
real database constraints and row locks. The WSGI HTTP test checks a direct HTTP
request and an explicitly trusted local proxy header; it does not deploy or certify
an operator's production TLS/reverse-proxy configuration. No production data or host
is modified, and the static scanner has not been rerun.

The authentication backend follows Django's [documented backend contract](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/).
