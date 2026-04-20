# Auth/RBAC Verification Report

**Date:** 2026-02-24  
**Scope:** Rigorous verification + hardening pass for RBAC/auth implementation

---

## Step 0 — Implementation Locations

| Component | Path |
|-----------|------|
| Migration | `backend/alembic/versions/018_add_rbac_tables.py` |
| Models | `backend/app/models.py` (User, Role, UserRole) |
| Auth module | `backend/app/security/auth.py` |
| RBAC bootstrap | `backend/app/security/rbac_bootstrap.py` |
| Auth router | `backend/app/routers/auth.py` (mounted at `/api/v1/auth`) |
| RBAC guards | Applied per-router or per-endpoint in: admin_forecast_methods, ingestion, imports_router, backbone_imports, plan_run, forecast, demand, stock_position, products, warehouses, suppliers, warehouse_products, supplier_products, projections, backbone_reports, lanes, planning_policies, inventory, receipts, timeline, exports, templates |
| Tests | `backend/tests/test_auth.py`, `backend/tests/test_rbac.py`, `backend/tests/test_rbac_bootstrap.py`, `backend/conftest.py` |
| Frontend | `frontend/src/api/auth.ts`, `frontend/src/stores/auth.ts`, `frontend/src/api/client.ts`, `frontend/src/App.vue`, `frontend/src/components/layout/LeftNav.vue`, `frontend/src/components/layout/TopBar.vue` |

---

## Step 1 — Dev vs Prod Gating (Verified & Hardened)

**Verified:**
- `ENVIRONMENT in {"dev","local"}` enables dev auth via `_is_dev_mode()`
- `get_auth_mode()` returns `"dev"` or `"easy_auth"` consistently

**Changes:**
- Added `get_auth_mode()` and use it in `get_current_user`
- In `parse_dev_headers`: when NOT dev mode and `X-Dev-User` present, log warning (no payload) and return `None`
- Dev auth parsing is only attempted when `get_auth_mode() == "dev"`

**Result:** Prod cannot be spoofed by X-Dev-User; dev/local cannot be locked out by prod logic.

---

## Step 2 — Easy Auth Header Parsing (Hardened)

**Changes:**
- Added `_safe_b64decode()`: handles missing padding, returns `None` on invalid base64 (no 500)
- Added `_extract_from_claims()`: extracts oid, email, name from `claims` list
- Claim types: `oid` from `objectidentifier`/`oid`; email from `preferred_username`/`upn`/`email`; name from `name`
- Invalid JSON/base64 returns `None` with logging; no exception propagation

**Result:** Resilient parsing for real Easy Auth shapes; invalid input does not crash.

---

## Step 3 — Upsert Logic + Role Resolution (Verified)

**Verified:**
- Upsert by `entra_oid` when present; else by `email` (dev)
- `last_login_at` updated on each auth
- Dev header `runtime_roles` are **runtime-only**, never persisted
- When no DB roles and no header roles in dev: default `["Viewer"]`

**Result:** Matches spec; no changes needed.

---

## Step 4 — RBAC Guard Coverage Audit

| Router | Guard | Endpoints |
|--------|-------|-----------|
| admin_forecast_methods | Admin | GET, POST acknowledge, GET acknowledgements |
| ingestion | Admin or Operator | All (upload, execute, list runs) |
| imports_router | Admin or Operator | All (inventory, receipts, demand, products, etc.) |
| backbone_imports | Admin or Operator | All (stock-positions, inbound-orders, demand-weekly) |
| plan_run | Admin or Planner (write) / Any auth (read) | run, patch, reset, overrides, freeze, unfreeze, recalculate; all GETs |
| forecast | Admin or Planner (write) / Any auth (read) | POST runs, POST metrics/recompute; all GETs |
| demand, stock_position, products, warehouses, suppliers, warehouse_products, supplier_products, projections, backbone_reports, lanes, planning_policies, inventory, receipts, timeline, exports, templates | Any auth | All |

**Result:** All routers have appropriate guards. No missing coverage.

---

## Step 5 — Tests (Expanded)

**Added tests:**

| Test | Purpose |
|------|---------|
| `test_parse_easy_auth_invalid_base64_returns_none` | Invalid base64 → None, no exception |
| `test_parse_easy_auth_base64_without_padding` | Base64 without padding works |
| `test_parse_easy_auth_claims_extraction` | Claims list yields oid, email, name |
| `test_get_auth_mode_dev` | `get_auth_mode()` returns "dev" for dev/local |
| `test_get_auth_mode_prod` | `get_auth_mode()` returns "easy_auth" for prod/stage |
| `test_prod_mode_x_dev_user_ignored_returns_401` | ENVIRONMENT=prod + X-Dev-User → 401 |
| `test_prod_mode_easy_auth_works` | ENVIRONMENT=prod + X-MS-CLIENT-PRINCIPAL → 200 |

**Result:** 21 auth/RBAC tests; 35 total including forecast_run_picker and stock_position. All pass.

---

## Step 6 — Frontend Safety Checks

**Changes:**
- Replaced `import.meta.env.DEV` with `import.meta.env.MODE !== "production"`
- X-Dev-User header only sent when `isNonProduction` is true

**Verified:**
- App renders even when auth fails; "Not signed in" banner shown
- Auth store calls `loadMe()` on mount

**Result:** Production build never sends X-Dev-User even if VITE_DEV_USER is set.

---

## File-by-File Changes

| File | Change |
|------|--------|
| `backend/app/security/auth.py` | Added `get_auth_mode()`, `_safe_b64decode()`, `_extract_from_claims()`; hardened Easy Auth parsing; dev header ignored in prod with warning |
| `frontend/src/api/client.ts` | Guard X-Dev-User on `MODE !== "production"` |
| `backend/tests/test_auth.py` | Added 6 tests (invalid base64, padding, claims, get_auth_mode) |
| `backend/tests/test_rbac.py` | Added 2 tests (prod X-Dev-User ignored, prod Easy Auth works) |
| `backend/tests/test_auth.py` | Removed unused `Identity`, `VALID_ROLES` imports |

---

## Remaining Risks

1. **Vite MODE:** `MODE` is set at build time. If a production build is run with `MODE=development` (e.g. staging), X-Dev-User could be sent. Mitigation: ensure production builds use `vite build` (default MODE=production).

2. **Easy Auth header shape:** Azure Easy Auth may vary by configuration. Our parser handles common shapes; edge cases may need adjustment if new shapes appear.

3. **Pre-existing test failure:** `test_baseline_forecast.py::test_forecast_same_week_last_year` fails (unrelated to auth). Likely due to forecasting logic change.

---

## RBAC Bootstrap (First-Admin)

**Env var:** `RBAC_BOOTSTRAP_ADMIN_EMAILS` (comma-separated emails, case-insensitive, trimmed)

**Behavior:** In non-dev environments (`auth_mode = easy_auth`), when `get_current_user()` upserts a user:
- If user has zero DB roles AND email is in allowlist → persist Admin role in `user_roles`
- Idempotent: does not duplicate if Admin already assigned
- Does NOT log the email list or full identity payload

**Module:** `backend/app/security/rbac_bootstrap.py`
- `parse_email_allowlist(raw)` → frozenset of allowed emails
- `bootstrap_admin_if_allowed(db, user, email)` → True if Admin was assigned

**Tests:** `backend/tests/test_rbac_bootstrap.py`
- `test_parse_email_allowlist` — parsing
- `test_prod_mode_bootstrap_admin_persisted` — admin in allowlist gets Admin
- `test_prod_mode_not_in_allowlist_no_roles` — user not in allowlist gets no roles
- `test_dev_mode_bootstrap_does_not_run` — dev mode: bootstrap skipped
- `test_bootstrap_idempotent` — second login does not duplicate

---

## Test Summary

```
tests/test_auth.py: 15 passed
tests/test_rbac.py: 7 passed
tests/test_rbac_bootstrap.py: 5 passed
tests/test_forecast_run_picker.py: 4 passed
tests/test_stock_position_breakdown.py: 9 passed
Total: 40 passed
```
