# License Service Specification

Status: Draft v3 (language-agnostic, agent-agnostic)

Purpose: A single-tenant HTTP service that lets privileged Admin accounts issue license keys
for multiple Products, and lets each Customer redeem a key to obtain Entitlement to a Product
and bind customer-generated Devices under that Entitlement.

## Normative Language

The key words `MUST`, `MUST NOT`, `REQUIRED`, `SHOULD`, `SHOULD NOT`, `RECOMMENDED`, `MAY`, and
`OPTIONAL` in this document are to be interpreted as described in RFC 2119.

`Implementation-defined` means the behavior is part of the implementation contract, but this
specification does not prescribe one universal policy. Implementations MUST document the selected
behavior.

## 1. Problem Statement

The License Service is a long-running HTTP process. It serves a machine HTTP API, a published
OpenAPI document, human-readable API documentation, and a first-party HTML UI (Admin console
and Customer self-service pages). One deployment licenses the operator's own Products. People
register as Customer Accounts, redeem Admin-issued License Keys, and manage Devices bound to
each Entitlement. Licensed Applications call the same process to bind and validate Devices.

The system solves four operational problems:

- There is no small, auditable implementation that is enough for a solo operator who sells
  several products and wants customers to self-manage device seats.
- The Admin needs one place to create Products and issue License Keys without a marketplace or
  a billing stack.
- A Customer needs to turn a key into access to one Product and bind several Devices whose
  identities the Customer (or their Licensed Application) generates.
- A Licensed Application needs a documented HTTP contract to bind and check a Device, and to
  generate its own client from OpenAPI.

Trust and safety posture: an Admin Account is a trusted operator of the instance. Customer
Accounts are authenticated and MUST be authorized only for their own records. Licensed
Applications and License Keys are untrusted inputs. Possession of a key or a `device_fingerprint`
MUST NOT be treated as proof of a particular physical machine. The License Store's Entitlements
and Device bindings are the source of truth. Implementations MUST document authentication,
secret storage, and abuse controls (Section 15).

Important boundary:

- Language-specific API clients are the caller's responsibility. The service MUST publish
  OpenAPI and human-readable API documentation.
- The service MUST NOT accept payments, store payment instruments, or talk to a billing
  provider. An external card-issuing platform only delivers a License Key the Admin already
  created.
- The service MUST NOT distribute installers, updates, or Product binaries.
- The service MUST NOT implement client-side anti-tamper, DRM, or hardware attestation.
- The service MUST NOT implement online checkout, usage metering, feature flags, organization
  accounts, a multi-vendor marketplace, floating/concurrent-session licenses, offline signed
  license files, heartbeat-based automatic seat release, outbound email, SMS, or webhooks.
- Unlocking a Licensed Application is the application's responsibility after it reads a
  validation result.
- After an Entitlement is created, the service MUST NOT provide operations that change
  `max_devices` or `expires_at`. Growing or shrinking seats after redeem is out of scope.

## 2. Goals and Non-Goals

### 2.1 Goals

- Stay small enough that a single operator can read, audit, and run the implementation.
- Let Admin Accounts manage licensing for multiple Products on one instance.
- Let Customers register with a username and password, redeem a License Key, and manage
  Devices bound to each Entitlement.
- Enforce a maximum Device count per Entitlement.
- Expose Admin, Customer, and Licensed Application operations over HTTP with a published
  OpenAPI document.
- Offer a first-party Admin HTML console and Customer HTML pages (register, login, redeem,
  entitlements, devices) so neither actor is required to use a raw HTTP client.
- Persist all authoritative state in an engine-agnostic License Store.
- Distinguish why a bind or validate call fails using the classes in Section 14.

### 2.2 Non-Goals

- Payment, invoicing, tax, or integrating the external card-issuing platform.
- Shipping installers, update channels, or Product artifacts.
- A first-party API client library in any language.
- Cryptographic proof that a `device_fingerprint` was produced by a particular machine.
- Offline license files, usage metering, feature entitlements beyond access to one Product,
  team or organization membership, a formal RBAC system beyond the Admin flag, multi-tenant
  Vendor isolation, or floating licenses.
- Contact channels: the service MUST NOT send email, SMS, or other messages, and MUST NOT
  require a verified address to register.
- Editing `max_devices` or `expires_at` on an existing Entitlement, stacking a second
  License Key onto the same (`account_id`, `product_id`), or automatically unbinding
  Devices when a limit would be exceeded.

## 3. System Overview

### 3.1 Main Components

1. `HTTP API`
   - Accepts Admin, Customer, and Licensed Application requests.
   - Serves the OpenAPI document and human-readable API documentation.
   - Enforces the authorization rules in Section 11.
2. `License Store`
   - Persists Accounts, Products, License Keys, Entitlements, and Devices.
   - Is the **single mutation authority**. Every create, update, and delete of those
     entities MUST go through the store in the same request that decides the outcome.
   - MUST be used through an engine-agnostic persistence layer so more than one durable
     engine can be documented and used.
3. `Authenticator`
   - Uses one Account record type for both Admin and Customer (Section 4.1.1).
   - Authenticates browser and API callers with a username, a password, and a server-side
     session. The password-hash and session-storage algorithms are Implementation-defined
     and MUST be documented.
   - Treats Licensed Application bind/validate calls as unauthenticated Account sessions;
     those calls authenticate by presenting a License Key and a `device_fingerprint`.
4. `HTML UI` (REQUIRED)
   - First-party browser pages served by the same process.
   - **Admin console:** MUST provide Admin operations from Section 11 without a separate
     HTTP client. MAY be generated from the License Store model. MUST be restricted to
     Admin sessions. MUST NOT show License Key plaintext after the issuing response, and
     MUST NOT show password hashes.
   - **Customer pages:** MUST provide register, login, logout, redeem License Key, list
     own Entitlements, and list / bind / unbind own Devices (optional display name).
     MUST NOT expose the unscoped Admin console. Implementation of these pages is
     Implementation-defined (they need not use the same generator as the Admin console).

There is no background worker, queue, or independent signing process in the core.

### 3.2 Abstraction Levels

A port MUST preserve these layers:

- Policy: redeem, bind, unbind, revoke, and seat limits. Owned by this spec.
- Coordination: HTTP operations, session context, and authorization checks.
- Persistence: durable records behind an engine-agnostic layer.
- Presentation: HTML UI and OpenAPI, derived from the same operations as the HTTP API.
- Observability: logs and documented error shapes.

Mechanism (HTTP framework, persistence engines, password hash, UI generator, logging
library) is Implementation-defined and MUST be documented.

### 3.3 External Dependencies

The host MUST provide:

- A process that listens for HTTP requests.
- At least one durable engine reachable through the License Store persistence layer.
  The set of supported engines is Implementation-defined and MUST be documented.
  Core Conformance (Section 17) MUST pass on every documented engine that the
  implementation claims to support.

The host MUST NOT need a payment provider, binary object store, or outbound mail.

Authenticator secrets, session secrets, and License Key plaintext MUST NOT be written to
logs or inherited by unrelated child processes.

## 4. Core Domain Model

Canonical terms. Use these words only, and only with the meanings below.

An **Account** is the stored person record. **Admin** means an Account with
`is_admin = true`. **Customer** means an Account with `is_admin = false` acting on its
own records. There is one Account system; there is not a separate Admin identity type.

A **Product** is one unit of software the operator licenses.

A **License Key** is a high-entropy opaque secret the Admin issues for exactly one
Product. The store keeps a hash, not the plaintext, after the issuing response.

An **Entitlement** is one Account's access to one Product. At most one Entitlement
exists per (`account_id`, `product_id`).

A **Device** is a binding of a caller-supplied `device_fingerprint` to one Entitlement.
The service assigns `device_id`. The Licensed Application MUST generate a
`device_fingerprint` that is unique per machine it runs on. The service does not
generate that fingerprint and does not attest hardware.

A **Licensed Application** calls bind and validate with a License Key and a
`device_fingerprint`. Unlocking the application is outside this spec.

### 4.1 Entities

#### 4.1.1 Account

- `account_id` (stable identifier)
  - REQUIRED. Assigned by the service at registration or Admin bootstrap.
  - MUST be unique on the instance. Format is Implementation-defined (Section 4.2).
- `username` (string)
  - REQUIRED. Unique on the instance after normalization (Section 4.2).
  - Used to log in. MUST NOT be treated as a contact channel.
- `password_hash` (secret)
  - REQUIRED. Algorithm is Implementation-defined and MUST be documented.
  - Plaintext passwords MUST exist only in the request that sets them.
- `is_admin` (boolean)
  - REQUIRED. Default `false` for self-registration.
  - `true` grants Admin operations. Core does not require more than one Admin Account.
    Additional Admin Accounts are Implementation-defined.
- `email` (string or null)
  - OPTIONAL. MUST NOT be required, verified, or used to authenticate.
- `created_at` (timestamp)
  - REQUIRED.

Self-registration MUST create a Customer Account (`is_admin = false`). Creating the
first Admin Account is a bootstrap step (Section 6) and MUST NOT be exposed as open
registration.

#### 4.1.2 Product

- `product_id` (stable identifier)
  - REQUIRED. Assigned by the service. Unique on the instance.
- `code` (string)
  - REQUIRED. Human-stable unique key for the Product (Section 4.2).
- `name` (string)
  - REQUIRED. Display label. Not used for authorization.
- `created_at` (timestamp)
  - REQUIRED.

#### 4.1.3 License Key

- `key_id` (stable identifier)
  - REQUIRED. Assigned by the service. Unique on the instance.
- `product_id` (identifier)
  - REQUIRED. The Product this key can entitle.
- `key_hash` (secret)
  - REQUIRED. Only a hash of the plaintext is stored after issue.
- `key_prefix` (string)
  - REQUIRED. A non-secret prefix of the plaintext so an Admin can recognize the key.
  - MUST NOT be sufficient to authenticate.
- `max_devices` (positive integer)
  - REQUIRED. Copied onto the Entitlement at redeem. MUST be >= 1.
- `expires_at` (timestamp or null)
  - OPTIONAL. Null means the resulting Entitlement does not expire.
- `status` (`issued` | `redeemed` | `revoked`)
  - REQUIRED. See Section 7.1.
- `redeemed_by_account_id` (identifier or null)
  - REQUIRED to be null while `status = issued`. Set on successful redeem.
- `created_at` (timestamp)
  - REQUIRED.

Plaintext form: a high-entropy opaque string. Generation is Implementation-defined and
MUST document entropy (RECOMMENDED: at least 128 bits of unguessable material plus a
fixed prefix). The plaintext is returned only in the issuing response (and MAY be shown
once in the Admin HTML UI at that moment).

#### 4.1.4 Entitlement

- `entitlement_id` (stable identifier)
  - REQUIRED. Assigned by the service. Unique on the instance.
- `account_id` (identifier)
  - REQUIRED.
- `product_id` (identifier)
  - REQUIRED.
  - The pair (`account_id`, `product_id`) MUST be unique.
- `max_devices` (positive integer)
  - REQUIRED. Copied from the License Key at redeem. MUST NOT change afterwards.
- `expires_at` (timestamp or null)
  - Copied from the License Key at redeem. Null means no expiry. MUST NOT change
    afterwards.
- `status` (`active` | `suspended` | `revoked`)
  - REQUIRED. See Section 7.2. Admin MAY change this field only.
- `source_key_id` (identifier)
  - REQUIRED. The License Key that created this Entitlement. MUST NOT change.
- `created_at` (timestamp)
  - REQUIRED.

#### 4.1.5 Device

- `device_id` (stable identifier)
  - REQUIRED. Assigned by the service. Unique on the instance. Used in Customer and
    Admin unbind calls.
- `entitlement_id` (identifier)
  - REQUIRED.
- `device_fingerprint` (string)
  - REQUIRED. Supplied by the Customer or Licensed Application. Opaque to the core
    after normalization (Section 4.2).
  - Among Devices that count toward the seat limit on one Entitlement, `device_fingerprint`
    MUST be unique.
- `display_name` (string or null)
  - OPTIONAL.
- `bound_at` (timestamp)
  - REQUIRED.
- `status` (`bound` | `unbound`)
  - REQUIRED. Only `bound` Devices count toward `max_devices`.

The Licensed Application MUST generate `device_fingerprint` values that are unique per
machine. The algorithm is Implementation-defined and MUST be documented. It MUST use
enough entropy that accidental collision between two machines of the same Customer is
negligible. The service MUST treat an identical normalized fingerprint on the same
Entitlement as the same Device (idempotent bind). The service MUST NOT claim that
uniqueness proves a physical machine.

### 4.2 Stable Identifiers and Normalization Rules

- `account_id`, `product_id`, `key_id`, `entitlement_id`, `device_id`
  - Opaque, unique on the instance, assigned by the service.
  - Format is Implementation-defined (for example a UUID or integer) and MUST be
    documented. MUST NOT be used as a secret.
- `username`
  - Trim leading and trailing whitespace. Compare and store uniquely in case-insensitive
    form (RECOMMENDED: Unicode case fold). Allowed charset and length are
    Implementation-defined and MUST be documented. Empty usernames MUST be rejected.
- `code` (Product)
  - Unique on the instance. Normalize by trimming whitespace. RECOMMENDED charset:
    `a-z`, `0-9`, hyphen; RECOMMENDED comparison: case-insensitive.
- License Key plaintext
  - Compare using the stored hash. Do not case-fold unless the documented generator
    emits a case-insensitive alphabet.
- `device_fingerprint`
  - Trim leading and trailing whitespace. MUST reject empty values after trim.
  - MUST NOT be HTML-decoded or otherwise rewritten.
  - Comparison is case-sensitive unless the implementation documents otherwise.
  - Maximum length is Implementation-defined and MUST be documented and enforced.
- `email`
  - If present, trim whitespace. MUST NOT be used as `username` or as a login identifier
    unless it happens to equal `username`.

## 5. Primary Input Contract

The primary input is the HTTP API. The instance's OpenAPI document is the discovery
source for methods and paths. Operation names in Section 11 are normative.

### 5.1 Transport and discovery

1. JSON request and response bodies for machine API calls (`Content-Type: application/json`
   on write). HTML UI form posts MAY use HTML form encoding; they MUST invoke the same
   store mutations as the corresponding JSON operations.
2. A URL prefix for the machine API is Implementation-defined. RECOMMENDED prefix: `/api`.
3. Concrete paths are Implementation-defined and MUST appear in the generated OpenAPI
   document. RECOMMENDED paths (under the API prefix) are listed with each operation in
   Section 11.
4. Browser and Customer/Admin JSON calls that require a session MUST use the
   Authenticator's server-side session cookie. `activate_device` and `validate_device`
   MUST NOT require that cookie.
5. The OpenAPI document MUST be served by the same process at an Implementation-defined
   path. RECOMMENDED: `/openapi.json`.
6. Human-readable API documentation MUST be served by the same process at an
   Implementation-defined path.

### 5.2 Parsing and unknown fields

- Missing body on a write that requires fields → `validation_error`.
- Body that is not the declared type (JSON object or form) → `validation_error`.
- Unknown fields on JSON write operations MUST be rejected with `validation_error`.
- Missing required fields, wrong types, empty `username`, empty `device_fingerprint`
  after trim, or `max_devices` < 1 → `validation_error`.

### 5.3 Error envelope

Every failed machine API call MUST use this object (field names normative):

```json
{
  "error": "seat_exhausted",
  "message": "This entitlement has no remaining device seats."
}
```

- `error` is one class from Section 14.1.
- `message` is human-readable and MUST NOT contain License Key plaintext, passwords, or
  session secrets.

HTTP status mapping (normative):

- 400: `validation_error`
- 401: `unauthenticated`
- 403: `forbidden`
- 404: `not_found`, `unknown_key`, `unknown_device`
- 409: `conflict`, `already_entitled`, `key_already_redeemed`, `key_revoked`,
  `seat_exhausted`, `entitlement_suspended`, `entitlement_revoked`,
  `entitlement_expired`
- 503: `store_unavailable`

`config_invalid` is startup-only and has no HTTP mapping.

### 5.4 Write-operation fields

Grouped by operation. Defaults apply when the field is omitted and OPTIONAL.
Changes apply immediately (there is no restart-gated API field).

`register`: `username` (string, REQUIRED), `password` (string, REQUIRED).

`login`: `username` (string, REQUIRED), `password` (string, REQUIRED).

`create_product`: `code` (string, REQUIRED), `name` (string, REQUIRED).

`update_product`: `name` (string, OPTIONAL). `code` MUST NOT change after create.

`issue_license_key`: `product_id` (identifier, REQUIRED), `max_devices` (integer,
REQUIRED, >= 1), `expires_at` (timestamp or null, OPTIONAL, default null).

`revoke_license_key`: `key_id` (identifier, REQUIRED).

`set_entitlement_status`: `entitlement_id` (identifier, REQUIRED), `status`
(`active` | `suspended` | `revoked`, REQUIRED). MUST NOT accept `max_devices` or
`expires_at`.

`redeem_license_key`: `license_key` (plaintext string, REQUIRED).

`bind_my_device` / `activate_device`: `device_fingerprint` (string, REQUIRED),
`display_name` (string, OPTIONAL). `activate_device` also requires `license_key`
(plaintext). `bind_my_device` also requires `entitlement_id` owned by the session.

`unbind_my_device` / `unbind_device`: `device_id` (identifier, REQUIRED).

`set_my_device_display_name`: `device_id` (identifier, REQUIRED), `display_name`
(string or null, REQUIRED).

`validate_device`: `license_key` (plaintext, REQUIRED), `device_fingerprint`
(string, REQUIRED).

## 6. Configuration Specification

### 6.1 Resolution pipeline

1. Locate configuration from an Implementation-defined source (settings module, file,
   environment, or a combination).
2. Parse. Syntax errors are `config_invalid`; startup MUST fail.
3. Apply documented defaults for omitted fields.
4. Resolve explicit indirection only: a setting MAY name an environment variable to
   read. Environment variables MUST NOT globally override a value that is already set
   in the primary source.
5. Coerce types and validate (Section 6.3). Failure is `config_invalid`.

### 6.2 Store settings (not a public URL)

The License Store needs to know **which durable engine to use and how to open it**.
That bundle of settings is called `store`. It is **not** the public URL of this HTTP
service.

`store` is Implementation-defined structured configuration. It MAY be a single
connection string, or a structured object (engine name, database name, user, host,
password, file path). Implementations MUST document the exact keys and give one
example per claimed engine.

Note: operators who use a persistence library typically fill in that library's
ordinary database settings. This spec only requires that those settings exist, are
validated at startup, and are documented.

Changing any `store` field MUST require a process restart.

### 6.3 Dynamic reload

Reload of `store` or `session_secret` is not required. If an implementation reloads
other fields, an invalid reload MUST keep the last valid values and MUST NOT crash
the process.

### 6.4 Preflight

At startup the process MUST: resolve configuration; refuse to listen on
`config_invalid`; open the License Store; apply pending store migrations if the
implementation uses them; fail startup if the engine is unreachable.

Per request: no extra config preflight. Authorization and Section 7 checks run on
each call.

Bootstrap: the operator MUST be able to create the first Admin Account out of band
(a documented management command or first-run of an empty store). That path MUST
NOT remain open as anonymous registration.

### 6.5 Core Config Fields Summary (Cheat Sheet)

This section is intentionally redundant so a coding agent can implement the config
layer quickly.

- `listen_host` (string, default Implementation-defined local bind)
- `listen_port` (integer, default Implementation-defined; MUST be documented)
- `store` (structured, REQUIRED) — engine identity and how to open it; see Section 6.2
- `session_secret` (secret string, REQUIRED in production) — MUST NOT have a
  hardcoded production default
- `debug` (boolean, default `false`)

## 7. Entitlement and Device State Machine

Internal names below are the only status values the core compares. They are distinct
from any HTML label.

### 7.1 License Key statuses

1. `issued` — created, plaintext no longer stored, not yet redeemed.
2. `redeemed` — bound to exactly one Account via `redeemed_by_account_id`.
3. `revoked` — MUST NOT be redeemed. Revoking an unused key does not create or alter
   an Entitlement. Revoking a redeemed key MUST NOT by itself change Entitlement
   status; the Admin revokes or suspends the Entitlement separately.

### 7.2 Entitlement statuses

1. `active` — bind and validate MAY succeed subject to seats and expiry.
2. `suspended` — bind and validate MUST fail with `entitlement_suspended`.
3. `revoked` — terminal. Bind and validate MUST fail with `entitlement_revoked`.

### 7.3 Device statuses

1. `bound` — occupies one seat.
2. `unbound` — does not occupy a seat. Terminal for that `device_id`. A later bind of
   the same fingerprint creates a new Device row (new `device_id`) if a seat is free.

### 7.4 Lifecycle of one redeem

1. Customer presents plaintext License Key while authenticated.
2. Lookup by hash. Missing or `revoked` → fail; no mutation.
3. `redeemed` by this Account → success, return the existing Entitlement (idempotent).
4. `redeemed` by another Account → fail; no mutation.
5. `issued` and this Account already has an Entitlement for that Product → fail
   (`already_entitled`); no mutation; the key stays `issued`.
6. `issued` and no Entitlement for that pair → create Entitlement (`active`, copy
   `max_devices` and `expires_at`), set key to `redeemed` and `redeemed_by_account_id`.
   Both writes MUST be atomic.

### 7.5 Lifecycle of one bind

1. Resolve the Entitlement: Customer session (own `entitlement_id`) or Licensed
   Application (License Key plaintext → redeemed key → Entitlement).
2. Entitlement missing, not `active`, or `expires_at` in the past → fail; no mutation.
3. Normalize `device_fingerprint`. Empty → fail.
4. A `bound` Device with that fingerprint on this Entitlement → success, return it
   (idempotent; MUST NOT increment seats).
5. Count of `bound` Devices on this Entitlement is already >= `max_devices` → fail
   (`seat_exhausted`).
6. Otherwise insert a `bound` Device.

### 7.6 Lifecycle of one unbind

1. Admin, or Customer who owns the Entitlement, presents `device_id`.
2. Missing or already `unbound` → idempotent success.
3. Set `status = unbound`. Seat count decreases.

### 7.7 Lifecycle of one validate

Read-only. Succeeds only if all are true: License Key hash matches a `redeemed` key;
its Entitlement is `active` and not expired; a `bound` Device exists on that
Entitlement with the presented fingerprint. Otherwise fail with the most specific
class in Section 14. Validate MUST NOT create rows.

### 7.8 Mutation authority and restart

Only the License Store mutates these rows, from the request that passed the
pre-checks above. A process restart restores all durable rows. Server-side sessions
are restored if the Authenticator's session store is durable; that durability is
Implementation-defined and MUST be documented.

## 8. Core Loop

Not applicable as a poll loop: the service is request/response.

Startup sequence:

1. Load and validate configuration (Section 6).
2. Open the License Store; fail startup if the engine is unreachable or migrations
   (if any) cannot apply.
3. Bind the HTTP listener.
4. Serve API, OpenAPI, documentation, and HTML UI.

There is no eligibility poll, retry backoff, or reconciliation worker. Seat and
status rules are checked on each bind, unbind, redeem, and validate.

## 9. Resource Management and Safety

### 9.1 Persistence

All entities in Section 4.1 live in the License Store. Naming of tables or collections
is Implementation-defined. Records MUST survive process restart.

Password hashes and `key_hash` values MUST persist. License Key plaintext MUST NOT
persist after the issuing response completes.

### 9.2 Safety Invariants

Invariant 1: At most one Entitlement per (`account_id`, `product_id`). Enforced by a
store uniqueness constraint and by Section 7.4 step 5.

Invariant 2: A License Key in `redeemed` has exactly one `redeemed_by_account_id`,
and that Account owns the Entitlement whose `source_key_id` is this key.

Invariant 3: The number of `bound` Devices on an Entitlement is never greater than
`max_devices`. Enforced in Section 7.5 steps 4–6, atomically with the insert.

Invariant 4: Self-registered Accounts have `is_admin = false`. Enforced in the
registration write.

Invariant 5: License Key plaintext and passwords are not logged and are not stored
in recoverable form after the request that accepted them.

Invariant 6: A Customer request MUST NOT read or write another Account's Entitlements
or Devices. Enforced by authorization using `account_id` from the session, not from
an untrusted body field.

Invariant 7: `max_devices` and `expires_at` on an Entitlement are immutable after
insert. Enforced by omitting write operations for those fields.

Invariant 6 is the primary portability constraint for any HTML generator: a
model-driven console that shows every row is an Admin-only tool.

## 10. External Protocol Integration

Not applicable: no peer protocol is the source of truth. The OpenAPI document is the
HTTP contract. Payment platforms are out of band and MUST NOT be integrated.

## 11. HTTP Adapter / Integration Contract

Operation names are normative. Paths are Implementation-defined; RECOMMENDED paths
assume prefix `/api`. Each implementation MUST publish a documented profile:
supported store engines, password-hash algorithm, session mechanism, Admin UI
generator, logging library, and `store` setting keys.

Empty list operations MUST return an empty collection, not an error. Omitted
OPTIONAL fields use defaults. Malformed bodies MUST fail with `validation_error`
and MUST NOT partially mutate. Redeem, bind, and unbind MUST be atomic per
Section 7.

The core MUST NOT inspect Licensed Application internals. Adapters beyond HTTP are
out of scope.

### 11.1 Admin session (`is_admin = true`)

1. `create_product` — RECOMMENDED `POST /api/products`
2. `update_product` — RECOMMENDED `PATCH /api/products/{product_id}`
3. `list_products` — RECOMMENDED `GET /api/products`
4. `get_product` — RECOMMENDED `GET /api/products/{product_id}`
5. `issue_license_key` — RECOMMENDED `POST /api/license-keys` — returns plaintext
   once; persists hash and prefix
6. `revoke_license_key` — RECOMMENDED `POST /api/license-keys/{key_id}/revoke`
7. `list_license_keys` — RECOMMENDED `GET /api/license-keys` — never plaintext
8. `list_accounts` / `get_account` — RECOMMENDED `GET /api/accounts`,
   `GET /api/accounts/{account_id}`
9. `list_entitlements` — RECOMMENDED `GET /api/entitlements`
10. `set_entitlement_status` — RECOMMENDED
    `POST /api/entitlements/{entitlement_id}/status`
11. `list_devices` — RECOMMENDED `GET /api/devices`
12. `unbind_device` — RECOMMENDED `POST /api/devices/{device_id}/unbind`

There is no `set_entitlement_max_devices` operation.

### 11.2 Customer session and anonymous registration

13. `register` — unauthenticated — RECOMMENDED `POST /api/auth/register`
14. `login` — unauthenticated — RECOMMENDED `POST /api/auth/login`
15. `logout` — session — RECOMMENDED `POST /api/auth/logout`
16. `redeem_license_key` — RECOMMENDED `POST /api/me/redeem`
17. `list_my_entitlements` / `get_my_entitlement` — RECOMMENDED `GET /api/me/entitlements`,
    `GET /api/me/entitlements/{entitlement_id}`
18. `list_my_devices` — RECOMMENDED `GET /api/me/entitlements/{entitlement_id}/devices`
19. `bind_my_device` — RECOMMENDED
    `POST /api/me/entitlements/{entitlement_id}/devices`
20. `unbind_my_device` — RECOMMENDED `POST /api/me/devices/{device_id}/unbind`
21. `set_my_device_display_name` — RECOMMENDED `PATCH /api/me/devices/{device_id}`

Customer `GET`/`POST` that include another Account's ids MUST return `forbidden` or
`not_found` and MUST NOT leak existence of foreign rows. RECOMMENDED: `not_found`.

### 11.3 Licensed Application (no Account session)

22. `activate_device` — RECOMMENDED `POST /api/activate`
23. `validate_device` — RECOMMENDED `POST /api/validate`

### 11.4 HTML pages (REQUIRED)

- Admin console: Implementation-defined paths, Admin session only.
- Customer pages: register, login, redeem, entitlement list, device list/bind/unbind.
  Paths are Implementation-defined.

## 12. Derived Artifact Construction

The OpenAPI document MUST be generated from the running HTTP implementation (or from
the same source that produces that implementation). A separately maintained handwritten
copy MUST NOT be the source of truth.

"Match" means all of the following:

- Every public machine operation the process serves appears in the document.
- Every Section 11 operation name appears as an `operationId` (or documented equivalent).
- A client generated from the document can call `register`, `login`, `redeem_license_key`,
  `activate_device`, and `validate_device` without undocumented fields.
- The error envelope in Section 5.3 is described.

Human-readable API documentation MUST exist and MUST NOT contradict the OpenAPI
document. HTML UI labels MUST NOT contradict operation semantics.

## 13. Logging, Status, and Observability

Logging MUST use the implementation language or HTTP framework's ordinary logging
library. Sinks, format, and rotation are that library's concern and are
Implementation-defined. Operators MUST still be able to see startup failures,
store-open failures, and authorization failures without a debugger.

REQUIRED context on every log record about a mutating or validate call (attached as
fields or structured extras the library supports):

- `actor` (`admin`, `customer`, `application`, or `anonymous`)
- `account_id` when a session exists
- `product_id` when known
- `entitlement_id` when known
- `device_id` when known
- `outcome` (success or the Section 14 class)
- an Implementation-defined request correlation id

MUST NOT log License Key plaintext, `key_hash`, passwords, or session secrets.
MUST NOT log raw `device_fingerprint`; log a truncated hash of the normalized
fingerprint if a device identifier is needed.

If the logging library's sink fails, the request's store mutation MUST still follow
Section 7; the request MUST NOT be failed solely because a log write failed.

Human-readable HTML is not required for correctness of bind/validate.

Metrics are OPTIONAL. If implemented, live seat counts MUST be read from the store,
not from a second counter that can drift.

## 14. Failure Model and Recovery Strategy

### 14.1 Classes

1. `validation_error` — malformed body, unknown field, empty fingerprint, bad types.
   No mutation.
2. `unauthenticated` — missing or invalid session where a session is required;
   missing key on application calls.
3. `forbidden` — authenticated but not allowed (Customer hitting Admin operations;
   Customer targeting another Account's ids).
4. `not_found` — unknown `product_id`, `device_id`, or similar, after authorization.
5. `unknown_key` — hash matches no License Key.
6. `key_revoked` — key `status = revoked`.
7. `key_already_redeemed` — key redeemed by a different Account.
8. `already_entitled` — Account already has an Entitlement for that Product and the
   presented key is a different `issued` key.
9. `entitlement_suspended` / `entitlement_revoked` / `entitlement_expired`
10. `unknown_device` — validate and no `bound` Device for that fingerprint.
11. `seat_exhausted` — bind of a new fingerprint when seats are full.
12. `conflict` — uniqueness clash (username, product `code`).
13. `store_unavailable` — engine error. MUST NOT partial-commit redeem/bind/unbind.
14. `config_invalid` — startup only.

### 14.2 Recovery

- Classes 1–12 are request-scoped; the process stays up.
- `store_unavailable` fails the request. The process SHOULD stay up and retry on
  later requests. Startup MUST fail if the store cannot be opened (Section 8).
- After restart, durable rows are the recovery. In-memory-only sessions, if used,
  are not restored; callers MUST `login` again. That choice MUST be documented.

Operator intervention: rotate `session_secret` (restart), create an Admin Account via
bootstrap, revoke unused keys, change Entitlement `status`, unbind Devices. There is
no operator action that edits Entitlement `max_devices` or `expires_at`.

## 15. Security and Operational Safety

Implementations MUST state: one operator-trusted deployment; Customers are
untrusted relative to each other; Licensed Applications are untrusted.

Mandatory:

- Store only password hashes and License Key hashes.
- Do not log secrets (Section 13).
- Invariants 4–7 in Section 9.2.
- Open registration cannot create `is_admin = true`.
- Model-generated HTML that can list every row MUST be restricted to Admin sessions.

RECOMMENDED hardening: rate-limit `login`, `register`, `redeem_license_key`,
`activate_device`, and `validate_device`; lock out after repeated `login` failures;
use HTTPS in production; choose a slow password hash.

Rate-limit thresholds are Implementation-defined and MUST be documented.

License Keys delivered by an external card platform are externally controlled
strings. Implementations SHOULD treat them like passwords (constant-time hash
compare, no reflection in error messages).

`device_fingerprint` is externally controlled. Implementations MUST bound its length
and MUST NOT interpolate it into queries or HTML without encoding.

## 16. Reference Algorithms (Language-Agnostic)

Pseudocode is illustrative. Normative rules are Sections 7 and 9.

```text
redeem(account, plaintext_key):
    key = store.find_key_by_hash(hash(plaintext_key))
    if key is missing: return unknown_key
    if key.status == revoked: return key_revoked
    if key.status == redeemed and key.redeemed_by_account_id == account.account_id:
        return ok(existing entitlement for source_key_id)
    if key.status == redeemed: return key_already_redeemed
    existing = store.find_entitlement(account.account_id, key.product_id)
    if existing is not missing: return already_entitled
    atomically:
        entitlement = insert Entitlement(active, copy max_devices, expires_at)
        key.status = redeemed
        key.redeemed_by_account_id = account.account_id
    return ok(entitlement)

bind(entitlement, fingerprint, display_name):
    if entitlement.status != active: return entitlement_*
    if entitlement.expires_at is not null and now > entitlement.expires_at:
        return entitlement_expired
    fp = trim(fingerprint)
    if fp is empty: return validation_error
    existing = store.find_bound_device(entitlement, fp)
    if existing is not missing: return ok(existing)
    atomically:
        if count_bound(entitlement) >= entitlement.max_devices:
            return seat_exhausted
        device = insert Device(bound, fp, display_name)
    return ok(device)

validate(plaintext_key, fingerprint):
    key = store.find_key_by_hash(hash(plaintext_key))
    if key is missing: return unknown_key
    if key.status != redeemed: return unknown_key or key_revoked
    entitlement = store.get_entitlement_by_source_key(key)
    if entitlement.status != active: return entitlement_*
    if expired(entitlement): return entitlement_expired
    device = store.find_bound_device(entitlement, trim(fingerprint))
    if device is missing: return unknown_device
    return ok(device)
```

## 17. Test and Validation Matrix

### 17.1 Profiles

- `Core Conformance` (REQUIRED, deterministic): in-process or local engine. Every
  bullet in Sections 17.2–17.8 that is not marked extension.
- `Extension Conformance` (REQUIRED if the HTML UI ships, which core requires):
  bullets that begin with `If HTML UI is implemented`.
- `Real Integration Profile` (RECOMMENDED): repeat Core Conformance against each
  documented store engine. Report skipped when the engine is not available.

### 17.2 Parsing and API contract

- Unknown JSON write field → `validation_error`, no mutation.
- Missing required field, empty fingerprint, `max_devices` < 1 → `validation_error`.
- Error body has `error` and `message`; `error` is a Section 14.1 class.
- HTTP status matches Section 5.3.
- `activate_device` and `validate_device` succeed without a session cookie when the
  key and fingerprint are valid.
- Session cookie is required for Customer and Admin operations other than
  `register` and `login`.

### 17.3 Resources and secrets

- After `issue_license_key`, list endpoints and the store have no plaintext key.
- Password plaintext is not persisted.
- Restart preserves Accounts, Products, keys (hash), Entitlements, Devices.

### 17.4 Adapter / authorization

- Customer cannot call Admin operations (`forbidden`).
- Customer cannot read or unbind another Account's Device (`not_found` or
  `forbidden`).
- `register` always yields `is_admin = false`.
- Duplicate `username` or Product `code` → `conflict`.

### 17.5 Redeem, bind, validate

- First redeem of an `issued` key creates one Entitlement and sets key `redeemed`.
- Same Account, same key again → same Entitlement, no second row.
- Other Account, already-redeemed key → `key_already_redeemed`.
- Second different `issued` key for the same Product → `already_entitled`; key stays
  `issued`.
- Revoked unused key → `key_revoked`.
- Bind new fingerprint occupies one seat; same fingerprint again is idempotent.
- Bind when `bound` count equals `max_devices` → `seat_exhausted`.
- Unbind then bind same fingerprint occupies a seat again.
- Validate succeeds only for `redeemed` key + `active` unexpired Entitlement +
  `bound` fingerprint.
- Validate does not insert rows.
- Suspended / revoked / expired Entitlement → the matching class; no bind.

### 17.6 Immutability and seats

- No HTTP operation changes Entitlement `max_devices` or `expires_at`.
- Invariant 3 holds under concurrent binds (or documented single-process serialization
  that still refuses the extra insert).

### 17.7 Observability and OpenAPI

- Generated OpenAPI lists every Section 11 machine operation as an `operationId`.
- OpenAPI is served by the process and matches Section 12.
- Logs for redeem/bind/validate include `actor` and `outcome`.
- Logs do not contain key plaintext, passwords, or raw fingerprints.

### 17.8 HTML / host lifecycle

- If HTML UI is implemented: unauthenticated Admin console URL does not expose
  other Customers' rows.
- If HTML UI is implemented: Customer can register, log in, redeem, and unbind a
  Device from the pages.
- Invalid configuration prevents listen (`config_invalid`).
- Unreachable store at startup prevents listen.

## 18. Implementation Checklist (Definition of Done)

### 18.1 REQUIRED for Conformance

- Engine-agnostic License Store; documented `store` settings and engines
  (`store`, no production default that hides the locator).
- `listen_host`, `listen_port`, `session_secret`, `debug` as in Section 6.5.
- Account passwords and sessions; Admin flag; open Customer registration; bootstrap
  Admin command.
- Product create/update/list/get; issue and revoke License Keys; redeem; bind;
  unbind; validate; set Entitlement status.
- Admin HTML console and Customer HTML pages listed in Section 3.1.
- OpenAPI generated from the implementation and served by the process.
- Human-readable API documentation that does not contradict OpenAPI.
- Error envelope and status mapping in Section 5.3.
- Invariants 1–7.
- Logging via the language or framework library, with Section 13 fields and secret
  redaction.

### 18.2 RECOMMENDED Extensions

- Rate limits and login lockout (Section 15).
- `Real Integration Profile` on every claimed engine.
- HTTPS termination documented for production.
- TODO: seat changes after redeem, stacked keys, contact channels — explicitly out
  of scope until a later spec revision.

### 18.3 Operational Validation Before Production

- Bootstrap one Admin Account; create one Product; issue one key; register a
  Customer; redeem; activate a Device; validate; unbind; revoke/suspend.
- Confirm list endpoints never return key plaintext.
- Confirm Customer pages cannot open the Admin console.
- Confirm `session_secret` is not the development default.
- Confirm the documented `store` settings actually open the intended engine.
