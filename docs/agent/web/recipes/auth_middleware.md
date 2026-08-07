# Recipe: auth_middleware

Domain: [WEB.md](../../WEB.md) · [auth_middleware.json](./auth_middleware.json)

## Intent

Protect a route with the project's existing auth pattern (session/JWT/middleware) — do not invent a new auth stack.

## Steps

1. Find existing auth middleware / guards in-repo
2. Apply same pattern to the target route
3. Verify unauthorized → expected status; authorized → OK
4. Memory: files + recipe id

## Verify

- [ ] Unauthenticated request rejected as project expects
- [ ] Authenticated happy path works
- [ ] No secrets committed

## Meta

`schema_version: 1` · `status: schematic` · `apply_mode: human`
