# NAVI-12: mypy clean-up — auto-generated Alembic migration trips 37 errors

**Complexity: low** (one config change in `pyproject.toml`; no source/runtime change.)

## Problem
`uv run mypy .` reports 37 `Module has no attribute "sql"` errors, ALL in the single
auto-generated migration `migrations/versions/939367c9ee06_initial_schema_spec_5.py`
(SQLAlchemy `sa.sql.*` references that mypy can't resolve). The configured run
(`uv run mypy`, which uses `files = ["src"]`) is already clean — the errors only appear because
the explicit `.` argument overrides the config and recurses into `migrations/`.

## Approach
Exclude the auto-generated `migrations/` tree from mypy via the `exclude` setting in
`[tool.mypy]` in `pyproject.toml`:

```toml
exclude = ["^migrations/"]
```

mypy applies `exclude` during recursive directory expansion (which `mypy .` triggers), so both
`uv run mypy` and `uv run mypy .` become clean. Rationale: Alembic migrations are generated
schema-op artifacts, not hand-maintained typed logic — excluding them from type-checking is
standard practice and removes noise without losing real safety on `src/`.

Keep `files = ["src"]` as-is (it already scopes the default run correctly).

## Key files
- `pyproject.toml` — `[tool.mypy]` section only. No source files change.

## Acceptance criteria
1. `uv run mypy .` → `Success: no issues found` (0 errors).
2. `uv run mypy` (bare) → still clean.
3. `uv run ruff check .` clean; full `uv run pytest` still green (no behavior change expected).
4. `uv run alembic upgrade head` still works (migration is excluded from type-checking, NOT deleted
   or modified — confirm the file is untouched).
5. No source/runtime change; only `pyproject.toml` `[tool.mypy]` edited.

## Out of scope / note
- Hand-written future migrations containing real logic could warrant targeted typing, but
  auto-generated schema ops do not. If that changes, narrow the exclude later.
