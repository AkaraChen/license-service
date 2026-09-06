"""License Service app.

MTV lives in three packages:

- `models/` — License Store records (Product, LicenseKey, Entitlement, Device)
- `templates/` — HTML for customer pages and Admin key issuance
- `views/` — customer pages and JSON API
- `admin.py` — Django Admin console (framework hook, stays at the app root)

Everything else at this root is not presentation or persistence:
accounts (auth), services (policy), app config.
"""
