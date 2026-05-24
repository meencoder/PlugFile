# Plugfile — Supabase setup (auth + save/resume)

This stands up authentication (Google / Facebook / Apple / email) and the
save/resume feature. Plugfile's code is already written against Supabase; these
are the one-time steps **you** perform (account/project creation and provider
registration can't be automated and need your credentials).

When these env vars are **unset**, Plugfile runs in *open mode* — no login,
nothing gated — so you can defer this entirely until you're ready.

---

## 1. Create the Supabase project

1. Sign up at <https://supabase.com> and create a new project (free tier is fine).
2. Note the **Project URL** (e.g. `https://abcd1234.supabase.co`) and the
   **anon/public key** under *Project Settings → API*. The anon key is
   **public by design** — RLS protects the data. Never expose the
   **service-role key** or the **JWT secret**.

## 2. Create the `filings` table

In the dashboard: **SQL Editor → New query**, paste the contents of
[`supabase/migrations/0001_filings.sql`](../supabase/migrations/0001_filings.sql),
and **Run**. This creates the table plus Row-Level Security so each user only
sees their own filings.

Then run [`supabase/migrations/0002_filing_shares.sql`](../supabase/migrations/0002_filing_shares.sql)
the same way — it adds operator→plugging-company **sharing**: an owner can share
one filing with a plugging company by email (the 🔗 button), and that company
can view + edit just that filing once they sign in with the matching address.
RLS still confines everyone else.

## 3. Enable sign-in providers

**Authentication → Providers**, then enable and configure:

- **Email** — works immediately (magic-link / one-time code). Easiest start.
- **Google** — create an OAuth client in the
  [Google Cloud Console](https://console.cloud.google.com/apis/credentials),
  add Supabase's callback URL (shown on the provider page), paste the client
  ID/secret into Supabase.
- **Facebook** — create an app at
  [developers.facebook.com](https://developers.facebook.com/), add Facebook
  Login, paste the App ID/secret into Supabase.
- **Apple** — requires a paid **Apple Developer** account: create a Services ID
  and a Sign-in key, generate the client secret, paste into Supabase. (Apple is
  the most involved; you can ship with Google + email first and add Apple later.)

Under **Authentication → URL Configuration**, add your site URL (and
`http://localhost:8000` for local dev) to the allowed redirect URLs.

## 4. Point Plugfile at the project

Add to your `.env` (see [`.env.example`](../.env.example)):

```
PLUGFILE_AUTH_PROVIDER=supabase
PLUGFILE_AUTH_JWKS_URL=https://YOUR-PROJECT.supabase.co/auth/v1/.well-known/jwks.json
PLUGFILE_AUTH_ISSUER=https://YOUR-PROJECT.supabase.co/auth/v1
PLUGFILE_AUTH_AUDIENCE=authenticated
PLUGFILE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
PLUGFILE_SUPABASE_ANON_KEY=eyJhbGciOi...your-public-anon-key...
```

> If your project still uses **legacy HS256** JWTs (older projects), switch to
> asymmetric keys under *Authentication → JWT Keys* (Supabase calls this
> "Migrate to asymmetric keys"). Plugfile verifies tokens against the public
> JWKS, so no secret is needed on the server.

Install the web extras so the backend can verify tokens:

```
pip install -e ".[web]"
```

## 5. Run and verify

```
plugfile-serve            # or: python -m plugfile.api
```

- `GET /api/auth/config` should now return `{"enabled": true, ...}`.
- The PWA header shows **Sign in: Google / Facebook / Apple / Email**.
- After signing in, a **💾 Save** / **📂 Resume** bar appears; saved filings
  round-trip through the `filings` table (visible under *Table Editor*).
- Downloading the **final (paid) PDF** now requires being signed in; the free
  DRAFT and all prep tools stay open.

---

## What's gated

| Action | Open mode | Auth enabled |
|---|---|---|
| Look up well, GAU/GW-2, AOR, plug program, attachments, portal format, district, handoff | open | open |
| Free **DRAFT** PDF | open | open |
| Final **paid** PDF (`paid_tier=true`) | open | **sign-in required** |
| **Save / resume** a filing | hidden | sign-in required |

## Security notes

- Only the **anon key** reaches the browser (via `/api/auth/config`); it's
  public by design. Keep the service-role key and JWT secret server-side only —
  Plugfile never needs them.
- Per-user data isolation is enforced by **RLS** in Postgres, not by client
  code, so a tampered client still can't read another user's filings.
