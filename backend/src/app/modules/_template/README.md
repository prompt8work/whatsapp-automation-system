# `_template`: copy this to start a new module

A small working module ("Item": create, rename, get) that shows the pattern every module follows.
It is **not installed**, so it has no routes in the running app and no migration.

```
_template/
├── module.py          what the module plugs into the platform (ModuleDefinition)
├── wiring.py          picks concrete classes: SQL Unit of Work → use cases → routers
├── contracts.py       the ONLY file other modules may import
├── domain/            rules: aggregate, events, errors, repository Protocols   (no frameworks)
├── application/       use cases: commands/, queries/, dto.py, unit_of_work.py    (no frameworks)
├── infrastructure/    tables.py, mappers.py, repositories.py, unit_of_work.py   (SQLAlchemy)
├── presentation/http/ schemas.py, routers.py                                    (FastAPI)
└── tests/             fakes.py + domain / use-case / HTTP tests                 (no database)
```

## Create a new module (cookbook §11.7)

1. `cp -r src/app/modules/_template src/app/modules/<name>`
2. In the new folder, replace `_template` with `<name>` in the imports, and rename `Item`/`template` to your concepts.
3. Add `"app.modules.<name>"` to the `containers` list of the layers contract in `pyproject.toml`.
4. Add `from app.modules.<name>.module import module as <name>_module` to `app/bootstrap/modules.py` and put it in `INSTALLED_MODULES`.
5. Import its `infrastructure/tables.py` in `alembic/env.py`, then `uv run alembic revision --autogenerate -m "<name>: initial"`, and call `enable_tenant_rls(...)` for each new table in the migration.
6. `uv run pytest && uv run lint-imports && uv run mypy`
