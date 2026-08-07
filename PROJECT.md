# Example — Web app project fingerprint (copy fields into PROJECT.md)

## Identity

| Field | Value |
|-------|-------|
| Name | ollama-dashboard|
| Pillar | `web` |
| One-line goal | Typed API + Next frontend for catalog items |
| Primary language(s) | TypeScript, Next.js |

## Stack — Web

- Framework: Next.js (App Router)
- Package manager: pnpm
- Node / runtime version: 20 LTS
- DB: Postgres (Prisma) — schema changes need human approve
- Important env files: `.env.local` (names only: `DATABASE_URL`, `AUTH_SECRET`)

## How to run / verify

```text
# Dev
pnpm dev

# Test / typecheck
pnpm lint
pnpm typecheck
pnpm test

# Build
pnpm build
```

## Layout

| Path | Meaning |
|------|---------|
| `app/` | Next App Router |
| `app/api/` | Route handlers |
| `lib/` | Shared server utils |

## Human-only gates

- Production deploy
- DB migrations
- Auth/security model changes
