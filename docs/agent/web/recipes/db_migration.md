# Recipe: db_migration

Domain: [WEB.md](../../WEB.md) · [db_migration.json](./db_migration.json)

## Intent

Add a DB migration using the project's tool (Prisma/Knex/EF/Laravel) after **human schema approval**.

## Steps

1. Confirm human approved schema change
2. Follow existing migration naming/tooling
3. Include rollback notes in memory
4. Run project migrate command from `PROJECT.md`
5. Never invent production data backfills without ask

## Verify

- [ ] Migration applies on clean DB
- [ ] Rollback notes written
- [ ] App typecheck still passes

## Meta

`schema_version: 1` · `status: schematic` · `apply_mode: human`
