# License Service (Django)

A single-tenant license key service implementing `SPEC.md` (Draft v3) on the Django
ecosystem: Django framework + ORM as the engine-agnostic License Store, Django Admin as
the Admin console, first-party Customer HTML pages, a JSON machine API, and an OpenAPI
document — all served by one process.

## Quickstart

```bash
uv sync
export LICENSE_DEBUG=1                         # explicit local development profile
uv run python manage.py migrate
uv run python manage.py createsuperuser        # bootstrap: the only way to create an Admin (6.4)
just serve                                     # migrate + Tailwind watcher + runserver (127.0.0.1:8000)
```

Customer HTML pages use Tailwind CSS 4 via [django-tailwind-cli](https://github.com/django-commons/django-tailwind-cli) (standalone CLI, no Node). Source is `src/styles.css`; the compiled sheet is `assets/css/tailwind.css`. Rebuild with `just css`, or let `just serve` watch.

Then open:

| URL | What |
| --- | --- |
| `/admin/` | Admin console (Django Admin, `is_staff` sessions only) |
| `/ui/register`, `/ui/login` | Customer self-service pages |
| `/` | Customer entitlement list (login required) |
| `/openapi.json` | OpenAPI 3.1 document, generated from Django URL patterns and view metadata |
| `/api/...` | JSON machine API (25 operations, SPEC Section 11) |

## Configuration (SPEC Section 6)

All configuration is environment variables; changing any `store` field requires a restart.

| Variable | Default | Meaning |
| --- | --- | --- |
| `LICENSE_LISTEN_HOST` / `LICENSE_LISTEN_PORT` | `127.0.0.1` / `8000` | bind address (passed to `runserver`) |
| `LICENSE_STORE_ENGINE` | `sqlite3` | `sqlite3` or `postgresql` |
| `LICENSE_STORE_NAME` | `./license_store.sqlite3` | sqlite file path, or database name |
| `LICENSE_STORE_USER` / `_PASSWORD` / `_HOST` / `_PORT` | — | postgresql only |
| `LICENSE_SESSION_SECRET` | dev default | **required** when `LICENSE_DEBUG=0` (no production default) |
| `LICENSE_DEBUG` | `0` | opt in with `1` for local development only |
| `LICENSE_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | comma-separated |
| `LICENSE_TRUST_PROXY` | `0` | set `1` only when a trusted edge strips/replaces `X-Forwarded-Proto` |
| `LICENSE_REGISTRATION_SOURCE_LIMIT` | `5` | registration attempts per direct peer per hour |
| `LICENSE_REGISTRATION_GLOBAL_LIMIT` | `100` | registration attempts across all sources per hour |
| `LICENSE_ACCOUNT_LIMIT` | `10000` | total account capacity for public registration |
| `LICENSE_DEVICE_HISTORY_LIMIT` | `100` | retained device rows per entitlement, at least its seat limit |

Preflight (6.4): `manage.py check` (also run by `runserver`) fails startup with
`config_invalid` when the production secret is missing (`licenses.E001`) and with
`store_unavailable` when the store engine cannot be opened (`licenses.E002`).
Unknown engines raise `ImproperlyConfigured("config_invalid: ...")` at settings import.

## Implementation-defined profile (SPEC Section 11)

- **Account**: `django.contrib.auth.models.User`. `account_id = User.pk` (integer,
  documented, never a secret), `is_admin = User.is_staff`, `created_at = date_joined`.
  One Account type for Admin and Customer. Admin bootstrap: `createsuperuser` only.
- **Password hash**: PBKDF2-SHA256 (Django default `PASSWORD_HASHERS`).
- **Session mechanism**: Django server-side sessions stored in the License Store DB
  (durable across restarts), cookie name `sessionid`, HttpOnly.
- **Store engines**: SQLite (default) and PostgreSQL, via the Django ORM. Core
  Conformance runs on SQLite; PostgreSQL is supported through the same ORM layer
  (run the suite with `LICENSE_STORE_ENGINE=postgresql` for the Real Integration
  Profile).
- **Admin UI generator**: Django Admin (`licenses/admin.py`).
- **UI language**: Django gettext, `en` and `zh-hans`. `LocaleMiddleware` picks
  the language from `Accept-Language`; there is no in-page switcher. Machine
  `error` class names stay English.
- **Logging library**: Python `logging`, logger `licenses.api`, console handler.
  Every JSON mutation/validation and HTML/Admin mutation logs a JSON record with
  `op`, `actor`, `outcome`, a request correlation id (`rid`), and known resource IDs
  (`account_id`, `product_id`, `entitlement_id`, `device_id`, or Admin object IDs).
  Client request IDs must match `[A-Za-z0-9_-]{1,64}`; other values are replaced.
  Logging never contains key plaintext, `key_hash`, passwords, session secrets, or raw
  fingerprints (Python logging handler failures never fail the request).
- **License Key generation**: `lic_` + 32 characters from a 29-symbol alphabet
  (`abcdefghjkmnpqrstuvwxyz23456789`, no look-alikes) from `secrets.choice`:
  ~155 bits of entropy. Only the SHA-256 hex digest and the first 12 characters
  (`key_prefix`) persist; plaintext is returned once in the issuing response.
- **Username**: trimmed, 1–150 chars, any charset, unique case-insensitively (ASCII
  case-insensitive on SQLite via database `LOWER`). A unique index enforces this
  across all writers; concurrent duplicate registration returns 409.
- **Product `code`**: trimmed, non-empty, unique case-insensitively.
- **`device_fingerprint`**: trimmed, must be non-empty, max 128 chars, case-sensitive,
  never HTML-decoded or rewritten. Generated by the Licensed Application; the service
  does not attest hardware.
- **Identifiers**: integer primary keys assigned by the store.
- **`validate_device`/`activate_device` on an `issued` (never redeemed) key**:
  reported as `unknown_key` so key existence is not leaked before redeem.
- **Revoking a redeemed key** sets the key `revoked` and leaves the Entitlement
  unchanged (7.1); validate then fails with `key_revoked`.
- **Concurrency (Invariant 3)**: the seat check and insert run in one transaction.
  PostgreSQL serializes concurrent binds with `SELECT ... FOR UPDATE` on the
  Entitlement row; SQLite serializes writers at the database level and a busy write
  retries the whole check-and-insert (bounded, 10 attempts). The current entitlement
  status/expiry is checked under the lock. Anonymous activation also locks and
  rechecks the key, in key-then-entitlement order.
- **CSRF policy**: the JSON API is `csrf_exempt` but every write requires
  `Content-Type: application/json`, including empty writes (send `{}`). Session
  writes and login/registration reject a supplied Origin unless it exactly matches
  the request origin. HTML/Admin forms use Django CSRF tokens.
- **Login abuse controls**: all password-login adapters (JSON, Customer UI, and
  Django Admin) share durable License Store counters. Five failed attempts within
  15 minutes lock the resolved account across all sources and the direct peer
  address across all accounts for 15 minutes. Account matching retains the
  trimmed, case-insensitive login behavior; only keyed digests are stored. A
  successful login clears the account counter but not unrelated failures from
  the same source. `REMOTE_ADDR` is the trusted peer boundary; forwarded-address
  headers are ignored, so a production proxy should supply/enforce client limits
  at its own trusted edge. Blocked callers receive the existing generic invalid-
  credentials response, counters inactive for 30 minutes are pruned, and existing
  sessions survive a lockout. Inactive accounts never authenticate; activation
  changes via the application invalidate their stored sessions.
- **Registration abuse controls**: durable source/global hourly attempt counters
  run before password hashing. Account creation serializes registration hashes
  across workers and checks the total account capacity under the same lock.
  At capacity or above an attempt limit, API registration returns 429. Stale source
  counters are pruned; forwarded client-address headers are never trusted.
- **Device storage**: display names are at most 200 characters, enforced by shared
  services and the database. A new binding prunes the oldest unbound rows when the
  per-entitlement history budget is full; bound rows are retained.
- **Request bounds**: bodies are limited to 16 KiB; registration passwords to 1,024
  characters. Invalid Unicode, null characters, nested JSON values, and expected
  parser/database errors return sanitized errors.
- **HTTPS**: production defaults to HTTPS redirects, Secure session/CSRF cookies,
  and one-year HSTS. Set `LICENSE_SESSION_SECRET` and `LICENSE_ALLOWED_HOSTS`;
  terminate TLS at your edge. Only enable `LICENSE_TRUST_PROXY=1` when that edge
  strips and replaces the scheme header and prevents direct upstream access.
  Development requires explicit `LICENSE_DEBUG=1` and a loopback listen setting.
- **One-time key delivery**: Admin single/batch issuance renders plaintext directly
  in the POST response with `Cache-Control: no-store`; no session, message cookie,
  or redirect handoff contains the key. JSON issuance is also non-cacheable.

## Error contract (SPEC 5.3 / 14)

Every failed machine call returns `{"error": <class>, "message": <str>}` with the
normative HTTP mapping: 400 `validation_error`; 401 `unauthenticated`; 403
`forbidden`; 404 `not_found`/`unknown_key`/`unknown_device`; 409 `conflict`,
`already_entitled`, `key_already_redeemed`, `key_revoked`, `seat_exhausted`,
`entitlement_suspended`, `entitlement_revoked`, `entitlement_expired`; 429
`rate_limited`; 503
`store_unavailable`. `config_invalid` is startup-only.


## Security upgrade

Apply migrations before starting the updated service. Migration `0004` clears all
existing sessions, including old key-delivery sessions; everyone must log in again.
It refuses to proceed if case-insensitive duplicate usernames exist, so the operator
must resolve their ownership before retrying. The device-name constraint likewise
requires existing names to fit the 200-character limit; names are never silently
truncated. Past backups may still contain plaintext issued by the old version and
must be retired according to the operator's backup policy.

The change also switches production defaults to HTTPS and a required secret. Set
production environment variables before `migrate` or importing WSGI. For local use,
follow the explicit development profile in Quickstart.

See [the finding-by-finding repair and validation record](docs/security-scan-2026-09-06.md).

## Code layout and audit budget

Code is formatted with `ruff format` and linted with `ruff check` (see `ruff.toml`,
line-length 110). Line counts below are **code lines measured by `scc`** (comments and
blank lines excluded).

The domain core — entities and invariants (`models.py`), the Section 7 state
machines (`services.py`), and the HTTP contract with validation, authorization, and
audit logging (`api.py`) — uses 21 explicit Django function views for 25 operations.
Validation, authorization, queries, response fields, and error handling are inline
so each view can be read without following helper wrappers. This deliberately
exceeds the original 500-line core target. Business rules, login/registration
limits, audit emission, and session invalidation retain their existing modules.
OpenAPI reads the Django URLconf and documentation-only `.openapi` attributes
beside the views.

| File | Code lines (scc) | Layer |
| --- | --- | --- |
| `licenses/models.py` | 74 | Persistence (entities, uniqueness invariants, login counters) |
| `licenses/services.py` | 188 | Policy (authentication/redeem/bind/unbind/validate, seats) |
| `licenses/api.py` | 1544 | Coordination (25 ops, validation, authz, logging) |
| **domain core subtotal** | **1806** | |
| `licenses/auth.py` | 135 | Authentication abuse controls |
| `licenses/registration.py` | 39 | Registration admission and hash serialization |
| `licenses/audit.py` | 59 | Shared audit emission |
| `licenses/signals.py` | 14 | Session invalidation |
| **core and security modules subtotal** | **2053** | |
| `licenses/openapi.py` | 75 | Presentation (OpenAPI from URLconf and view metadata) |
| `licenses/views_ui.py` | 118 | Presentation (Customer HTML pages) |
| `licenses/admin.py` | 155 | Presentation (Admin console config) |
| `licenses/apps.py` | 25 | Startup preflight checks |
| `config/`, `manage.py` | 214 | Standard Django project scaffolding |
| `licenses/templates/` | — | HTML (Django templates + Tailwind) |
| `src/styles.css` | — | Tailwind source (compiled to `assets/css/tailwind.css`) |
| `licenses/tests/` | 1680 | pytest suite (not counted as core) |

Reproduce: `scc --no-cocomo --no-size licenses/models.py licenses/services.py licenses/api.py`

## Tests

```bash
uv run pytest                 # SQLite suite; explicit test profile
uv run ruff format --check . && uv run ruff check .   # style and lint gates
```

Tests are organized by SPEC Section 17:

- `test_api_views.py` — explicit routes, HTTP methods, documented authentication and
  write fields, timestamp precision, database errors, and audit outcomes.
- `test_parsing.py` — 17.2: unknown/missing/typed fields, envelope shape, status
  mapping, session requirements, empty-list behavior.
- `test_authz.py` — 17.4: Admin vs Customer authorization, cross-account secrecy
  (foreign rows answer `not_found`), registration can never create an Admin,
  `conflict` on duplicate username/code.
- `test_redeem_bind_validate.py` — 17.5: the full redeem/bind/unbind/validate state
  machines, idempotency, seat exhaustion, suspension/revocation/expiry.
- `test_secrets.py` — 17.3: key plaintext and password hashes never persist or leak;
  cross-process restart durability; durable sessions.
- `test_immutability.py` — 17.6: no operation mutates `max_devices`/`expires_at`;
  8-thread concurrent bind race never exceeds `max_devices`.
- `test_openapi_logs.py` — 17.7: served OpenAPI lists every operationId and matches
  the running URLconf; audit logs carry `actor`/`outcome`/`rid` and never secrets.
- `test_html.py` — 17.8: Admin console gating, Customer page flow
  (register → redeem → bind → unbind), no Admin console exposure, plaintext shown once.
- `test_config.py` — 17.8: `config_invalid` and unreachable store prevent startup.

## Operational validation before production (SPEC 18.3)

```bash
python manage.py check                                  # preflight passes
python manage.py createsuperuser                        # bootstrap Admin
# Admin console: create one Product, issue one key (plaintext flashed once)
# Customer pages: register, redeem, bind a device, unbind it
curl -X POST localhost:8000/api/validate -H 'Content-Type: application/json' \
     -d '{"license_key": "...", "device_fingerprint": "..."}'
# Confirm /api/license-keys never returns plaintext; /admin/ redirects non-Admins;
# LICENSE_SESSION_SECRET is set and not the development default.
```
