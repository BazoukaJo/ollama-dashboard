# Recipe: next_zod_api

Domain: [WEB.md](../../WEB.md) · [next_zod_api.json](./next_zod_api.json)

## Intent

Typed Next.js App Router API with Zod body parse and JSON error shape.

## Steps

1. Match existing `app/api` patterns in-repo
2. Apply contract (safeParse → 400 JSON / 200 JSON)
3. Run `PROJECT.md` lint/typecheck/test
4. Memory: route path + recipe id

## Verify

- [ ] Invalid body → 400 JSON
- [ ] Valid body → 200 JSON
- [ ] Lint/typecheck pass

## Meta

`schema_version: 1` · `status: schematic` · `apply_mode: human`
