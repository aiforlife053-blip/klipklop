# Security Implementation Status

## Implemented

### P0 - Startup Guard
- `SECURITY_MODE` supports `local`, `private`, `public`.
- Server refuses non-`127.0.0.1` bind unless `SECURITY_MODE=public`.

### P1 - Supabase Auth
- Dashboard and `/api/*` require login.
- Login uses Supabase email/password.
- Session stored in `HttpOnly`, `SameSite=Lax` cookie.
- Configure placeholders in `config.json`:
  - `supabase_url`
  - `supabase_anon_key`

### P2 - Security Headers
- CSP
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy`
- `X-Frame-Options: DENY`

### P3 - API Hardening
- Body size limits on sensitive endpoints.
- Unknown endpoints return 404.

### P4 - URL/Download Safety
- YouTube domain validation.
- Output path validation.

### P5 - Job Control
- Single active job.
- Job timeout.

### P7 - Static File Serving
- Blocks sensitive extensions.
- HTML uses `Cache-Control: no-store`.

## Test Result

```text
31 passed, 1 failed
```

Failing test is pre-existing subtitle chunk behavior, unrelated to Supabase login.

## Remaining

- Add CSRF token for POST if deployed publicly.
- Add failed-login rate limit.
- Move secrets out of `config.json` for production.
- Rotate API keys already exposed locally/screenshots.
