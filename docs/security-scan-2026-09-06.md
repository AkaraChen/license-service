# Security scan remediation

Source: `codex-security-license-service-gTPBEt/report.md`, revision
`0c2348a16552baf9c0e2a36cc499beb8bd652119`. Numbers below follow the report's table,
not the ordering of `findings.json`. The original scan was static; these repairs
add executable adversarial and integration coverage.

| # | Finding | Repair | Regression evidence |
| --- | --- | --- | --- |
| 1 | Unbounded registration | django-ratelimit peer/global decorators with Redis; django-redis registration lock; total account capacity | Account-capacity response and concurrent identity creation |
| 2 | Unlimited password guesses | django-axes account/source lockouts, shared Redis cache and package middleware for API, HTML and Admin | Uses the package authentication backend, signals and middleware; no duplicated counter/TTL tests |
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
| 13 | Login timing enumeration | Missing, inactive and active wrong-password attempts all pass through backend hasher work | Delegates password verification to Django ModelBackend; application tests cover active/inactive login results |

## Upgrade behavior

- Configure the production secret, allowed hosts and TLS edge before starting.
- Run migrations. Existing sessions are invalidated once by `0003`; account data
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

## Rate-limit dependencies

Login counters and lockouts are handled by django-axes 8.3.1. Registration limits
use django-ratelimit 4.1.0. django-redis 6.0.0 provides the shared cache and a
registration lock. No project-owned throttle table, counter, expiry loop or SQLite
counter-retry implementation remains. The migration sequence upgrades from the
released `0001_initial` baseline.

All workers must share Redis and the cache namespace. Use persistent Redis with
no eviction; the included Compose service enables AOF and `noeviction`. Clearing
Redis resets limits. Authentication and registration fail closed when Redis is
unavailable. Successful logins do not reset failure counters; counted failures
refresh their 15-minute TTL, while already-blocked attempts do not extend it.

## Validation results

- Application suite with SQLite and Redis 7: **116 passed, 2 skipped**
  (PostgreSQL-only authorization lock ordering).
- Application suite with PostgreSQL 17 and Redis 7: **118 passed**.
- Ruff lint/format, Django system checks, migration drift, Compose configuration
  and whitespace checks pass. Both suites report three existing django-unfold
  deprecation warnings.

## Verification scope

The tests exercise SQLite, a disposable local PostgreSQL 17 instance and real Redis 7,
including application-owned database constraints, authorization and interface responses.
Third-party rate-limit algorithms, counters, TTL and hashing internals are not
retested in the repository. The WSGI HTTP test checks a direct HTTP
request and an explicitly trusted local proxy header; it does not deploy or certify
an operator's production TLS/reverse-proxy configuration. No production data or host
is modified, and the static scanner has not been rerun.

The authentication backend follows Django's [documented backend contract](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/).

Package contracts: [Axes configuration](https://django-axes.readthedocs.io/en/stable/4_configuration.html),
[django-ratelimit cache requirements](https://django-ratelimit.readthedocs.io/en/stable/installation.html).
