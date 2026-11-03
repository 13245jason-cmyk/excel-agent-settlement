# Neon connection setup for the Streamlit app

This remains a Python/Streamlit application using SQLAlchemy + psycopg. npm scripts are a command bridge, not a replacement frontend. Changes are prepared on Git `staging` only.

## Linked resources

The user-selected context is:

- Organization: `org-cold-bar-87741784`
- Project: `muddy-smoke-07523588`
- Neon database branch: `production`
- Requested service: Postgres only. Google OIDC remains the app's existing login provider; Managed Better Auth is not enabled.

The Neon branch name `production` does not authorize changing the website's Git `main` branch.

## CLI workflow

```bash
npm i -g neon@latest
neon init -y --org-id org-cold-bar-87741784 --project-id muddy-smoke-07523588 --branch production --services postgres
neon login
neon deploy
```

If global installation is unavailable, use `npx neon@latest` instead of `neon`. `neon init` can create `.neon` and `neon.ts` offline; that alone does not verify access or deploy anything. Never replace the specified project with a new claimable database after an authentication failure.

After successful deployment, CLI-managed `.env.local` (or an existing `.env`) should contain `DATABASE_URL` and `DATABASE_URL_UNPOOLED`. Do not print them or commit them. `.neon`, `.env*` and `node_modules/` are ignored by Git.

## Python wiring

`runtime_database.database_url()` supports:

1. Existing Streamlit Secrets `approval_db.url` (preserve an explicit existing binding).
2. `APPROVAL_DATABASE_URL` / `DATABASE_URL` for runtime traffic.
3. For schema initialization, prefer `APPROVAL_DATABASE_URL_UNPOOLED` / `DATABASE_URL_UNPOOLED`.

Local `.env.local` is loaded before `.env`; already-injected process variables win over both. Runtime traffic uses the pooled URL supplied by Neon; schema initialization uses the direct URL when available. PostgreSQL connections retain certificate and hostname verification (`verify-full`). No connection strings are written into source files or logs.

Streamlit Community Cloud does not receive a developer machine's ignored `.env.local` through Git. Its Secrets or actual process environment must be configured separately with the connection binding. Google OAuth and management-app configuration are still required before switching `access.login_method` to `google`.

## Build, start, and prove the service

```bash
python3 -m venv .venv
# Activate .venv, then:
pip install -r requirements.txt
npm ci
npm run build
npm start -- --server.port 8506
```

`npm run build` compiles the application Python files and runs the full test suite, preserving failures. It does not claim to create a Next.js frontend bundle. `npm start` starts `staging_app.py`; it does not deploy the formal website.

After `neon deploy` successfully provides the real connection variables, set the non-secret `APPROVAL_ADMIN_EMAIL` to the intended administrator's Google email, then run:

```bash
npm run db:init
npm run db:check
```

`db:init` creates only the app's approval tables through the direct connection. `db:check` verifies TLS/query access and the request → approve → environment-isolation → revoke lifecycle against the selected real database. It creates a unique synthetic identity and removes only that invocation's synthetic grant/audit rows afterward. It never deletes unrelated records. Run this only against the user-selected Neon project.

A passing local test suite or HTTP health request is not proof of a working Neon connection. `NEON SERVICE CHECK PASSED` is emitted only after the real database lifecycle completes.

## Current observed blockers

- CLI installation succeeded (`neon 8.17.1`). The requested `init` completed **offline and unverified**.
- `neon deploy` and `neon login` failed to reach the API. A proxy-routed request to `https://console.neon.tech/api/v2` returned HTTP 403 at CONNECT.
- Runtime network policy currently has no custom allowed hosts. A draft adding `console.neon.tech`, `oauth2.neon.tech`, and `neon.com` was saved; the configuration tool reports that user review/save and publication are still required. Saving a draft is not applying the runtime policy.
- The CLI default profile reports `account: "-"`, `file: "missing"`. No API key or database URL was present. No credentials were extracted from browser sessions.
- No `.env.local` / `.env` was pulled, no real database schema was initialized, and the actual Neon service check is not yet successful.

After the network policy is applied, complete `neon login` in this same execution environment and its official browser flow, then retry `neon deploy`, `db:init`, and `db:check`. Do not disable TLS or bypass the proxy. Once the Neon endpoint is known, any required TCP/5432 network grant must also be configured before native PostgreSQL can connect from this execution environment.
