# Authentication & Tenant Security Report

## 1. Authentication Security Model
- **Token Mechanism:** HS256 JWT access tokens signed with a server-side secret key (`JWT_SECRET_KEY`).
- **Identity Derivation:** The authenticated caller identity (`user_id`, `email`, `tenant_id`, `role`) is extracted solely from the cryptographically verified JWT payload.
- **Credential Storage:** User passwords stored in Neon PostgreSQL are hashed using `bcrypt` (`passlib.context.CryptContext(schemes=["bcrypt"])`). Plaintext passwords are never logged or stored.

## 2. Server-Side Tenant Authorization
- The backend FastAPI dependency `get_authorized_tenant` strictly intercepts all requests.
- If an `X-Tenant-ID` header is provided by the client, it is compared against the user's authorized `tenant_id` claim in the verified JWT.
- **Spoofing Defense:** If an authenticated user belonging to `tenant-alpha` supplies `X-Tenant-ID: tenant-beta`, the request is immediately rejected with `403 Forbidden` (`Access denied: User ... is not a member of tenant ...`).
- **Unauthenticated Defense:** If no `Authorization: Bearer <token>` is provided, the API fails closed with `401 Unauthorized`.

## 3. Automated Test Verification
All 10 security audit tests in `tests/test_auth_security.py` pass cleanly:
- `test_1_missing_credentials_fails_401`: Verified.
- `test_2_invalid_token_signature_fails_401`: Verified.
- `test_3_expired_token_fails_401`: Verified.
- `test_4_authorized_tenant_a_access_permitted`: Verified.
- `test_5_tenant_a_spoofing_tenant_b_header_denied_403`: Verified.
- `test_6_tenant_a_requesting_tenant_b_chunks_denied_404`: Verified.
- `test_7_authorized_tenant_b_access_permitted`: Verified.
- `test_8_login_endpoint_generates_valid_jwt`: Verified.
- `test_9_metrics_summary_scoped_and_redacts_global_tenants`: Verified.
- `test_10_sql_injection_defense_under_authenticated_context`: Verified.
