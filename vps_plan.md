# VPS Multi-User Plan

## 1. Authentication

- Create exactly five users through Supabase Admin.
- Disable public signup in Supabase and remove the `/api/signup` endpoint.
- Replace email-based custom sessions with validated Supabase JWTs and stable user UUIDs.
- Set authentication cookies to `Secure`, `HttpOnly`, and `SameSite=Lax`.

## 2. User Isolation

- Store user files under `data/<user_uuid>/{output,config,cookies,watermark}`.
- Restrict every list, download, stream, save, delete, and upload operation to the authenticated user's directory.
- Isolate status, logs, activity history, and OAuth state by user UUID.
- Reject path traversal and cross-user resource access.

## 3. Processing Queue

- Use one global worker queue to conserve VPS CPU and memory.
- Associate every job with its owner's user UUID.
- Allow users to view and cancel only their own jobs.
- Keep queue position, progress, logs, and output private per user.

## 4. Provider API Keys

- Store each user's Gemini/provider API keys in Supabase Vault.
- Store only Vault secret references in `user_settings`.
- Protect settings with RLS using `auth.uid() = user_id`.
- Access Vault only from the backend using a service-role key stored in VPS environment variables.
- Never return provider keys through APIs or write them to logs.

## 5. YouTube OAuth

- Use a fixed HTTPS callback such as `https://<domain>/api/youtube/callback`.
- Generate random, single-use OAuth state tied to the initiating user UUID and an expiration time.
- Isolate each user's YouTube channel connection and tokens.
- Encrypt refresh and access tokens; do not identify token files by email or store tokens as plaintext.
- Support concurrent OAuth attempts without shared callback state.

## 6. VPS Deployment

- Put the application behind Caddy or Nginx with HTTPS.
- Store all application, Supabase, OAuth, encryption, and session secrets in environment variables.
- Add login rate limiting, upload-size limits, per-user disk quotas, and database backups.
- Rotate credentials and tokens previously stored in the workspace or Git history.
- Restrict direct application-port access through the VPS firewall.

## 7. Main Changes

- `server.py`: JWT validation, UUID identity, authorization checks, secure cookies, and HTTPS OAuth callback.
- `job_manager.py`: global queue with user-owned jobs and isolated runtime state.
- `social_auth.py`: fixed callback URL, per-user OAuth transactions, and encrypted credentials.
- `frontend/src/pages/Login.tsx`: remove public signup and handle authenticated sessions.
- Supabase migration: user settings, OAuth connections, job metadata, Vault references, indexes, and RLS policies.

## 8. Verification

- User A cannot list, download, stream, delete, modify, or upload User B's files.
- Jobs use one global queue while progress, logs, cancellation, and outputs remain isolated.
- Concurrent OAuth attempts cannot exchange users or channels.
- Vault keys and YouTube tokens never appear in API responses or logs.
- Test logout, user disablement, token expiry, path traversal, CSRF protection, rate limits, and disk quotas.
