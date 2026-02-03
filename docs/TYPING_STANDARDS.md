# Typing Standards & Pyright Guide

> Purpose: eliminate "partially unknown" types, prevent runtime foot‑guns, and keep our services shippable under strict Pyright.

These rules are **mechanical**. Follow them and Pyright will be quiet. Break them and CI will fail.

---

## Core Rules (must)

### 0. **Default File Scaffolding (MANDATORY)**
Every Python file must start with this standard scaffolding:
```python
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)
```

**Why this matters:**
- **Consistency**: Every file follows the same pattern
- **Future-proofing**: All files ready for logging when needed  
- **Type safety**: Consistent future annotations across all files
- **Developer experience**: New developers know exactly what to expect
- **Maintenance**: Easier to enforce standards with automated tools

**Implementation:**
- Use the `add_default_scaffolding.py` script to add this to all files
- Pre-commit hooks will enforce this pattern
- New files must include this scaffolding from the start

### 1. **Enable future annotations in every Python file**
```python
from __future__ import annotations
```
*Why*: avoids runtime import cycles and allows forward references without quotes across 3.10–3.12.

### 2. **Never use bare generics**
- ❌ `list`, `dict`, `set`, `tuple`, `Dict`, `List`, …
- ✅ `list[str]`, `dict[str, int]`, `tuple[int, ...]`
- If you don't know yet: temporarily use `dict[str, Any]` (not `object`) and file a TODO to replace with a `TypedDict`.

### 3. **Match nullable defaults with Optional and normalize**
```python
from typing import Optional

def f(items: Optional[list[str]] = None) -> list[str]:
    normalized: list[str] = items or []
    return normalized
```

### 4. **Never use mutable default arguments**
- ❌ `def f(items: list[str] = []) -> None: ...`
- ✅ `def f(items: Optional[list[str]] = None) -> None: items = items or []`

### 5. **For parameters use abstract containers; for return types use concretes**
```python
from collections.abc import Iterable, Mapping

def ingest(tags: Iterable[str], metadata: Mapping[str, str]) -> None: ...
def list_tags() -> list[str]: ...
def metadata() -> dict[str, str]: ...
```

### 6. **Every function declares an explicit return type**
- `-> None` for procedures.
- Avoid implicit `Any` at call sites.

### 7. **Prefer structured payloads**
- External/public or cross‑module shapes: `TypedDict` or Pydantic models.
- Internal scratch blobs: `dict[str, Any]` for speed *only* during refactors.
- If you keep `object`, immediately narrow with `isinstance` or `typing.cast` before use.

### 8. **SQLAlchemy typing (2.x)**  
- Models use `Mapped[...]` + `mapped_column(...)` for fields.  
- Queries use `.scalars()` and annotate returns.

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int]

async def load_users(db: AsyncSession, org_id: int) -> list[User]:
    res = await db.execute(select(User).where(User.organization_id == org_id))
    return list(res.scalars())

async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)
```

### 9. **Async functions are explicit about types at boundaries**
- Handler/service inputs and outputs are fully annotated.
- Background tasks return `None` unless a typed result is consumed.

### 10. **Docstring examples match annotations**
- If a docstring shows a key, the `TypedDict` or return type includes it.

---

## File Structure Standards

### Standard File Header
Every Python file must follow this exact structure:

```python
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# Rest of imports (standard library, third-party, local)
from typing import Optional, Dict, Any
from pathlib import Path
from fastapi import APIRouter
from app.core.database import get_db

# Module-level constants
CONSTANT_VALUE = "example"

# Classes and functions
class MyClass:
    def __init__(self) -> None:
        pass

def my_function(param: str) -> Optional[str]:
    return param
```

### Import Order
1. `from __future__ import annotations` (always first)
2. `import logging` (always second)
3. `logger = logging.getLogger(__name__)` (always third)
4. Standard library imports
5. Third-party imports  
6. Local application imports

---

## Any vs object (be intentional)
- `Any` is useful for rapid refactors; it disables type checking downstream. Use *sparingly* and replace soon.
- `object` blocks accidental attribute access but requires narrowing. Good for public APIs that accept "anything".

**Rule of thumb**
- Internal, short‑lived: `dict[str, Any]`
- Public/cross‑module: `TypedDict`/Pydantic
- Accepting unconstrained inputs: `object` + narrowing

---

## TypedDict quick patterns

### Optional keys with strict values
```python
from typing import TypedDict, Literal

class Reminder(TypedDict):
    minutes_before: int
    type: Literal["email", "in_app"]

class EventData(TypedDict, total=False):
    title: str
    description: str | None
    type: str
    status: str
    related_type: str | None
    related_id: str | None
    start_at: datetime
    end_at: datetime | None
    all_day: bool
    timezone: str
    recurrence_rrule: str | None
    owner_id: int
    attendees: list[int]
    reminders: list[Reminder]
    location: str | None
    meeting_url: str | None
    color: str | None
    tags: list[str]
```

### Result envelopes
```python
class SyncResult(TypedDict):
    tasks_processed: int
    events_created: int
    events_updated: int
```

---

## Calendar / AV examples (before → after)

**Before**
```python
def scan_file(path, engine, threats: list = None) -> Dict:
    return {"engine": engine, "threats": threats}
```

**After**
```python
from typing import Optional, TypedDict

class ScanResult(TypedDict):
    engine: str
    infected: bool
    threats: list[str]

def scan_file(path: Path, engine: str, threats: Optional[list[str]] = None) -> ScanResult:
    t: list[str] = threats or []
    return {"engine": engine, "infected": bool(t), "threats": t}
```

---

## Pyright configuration

`pyrightconfig.json` (root):
```json
{
  "typeCheckingMode": "strict",
  "reportMissingTypeArgument": "error",
  "reportUnknownParameterType": "error",
  "reportUnknownMemberType": "error",
  "reportUnknownVariableType": "error",
  "reportUnknownArgumentType": "error",
  "venvPath": "venv",
  "exclude": ["**/node_modules", "**/__pycache__", "venv"]
}
```

> You can temporarily lower specific rules to `"warning"` during large refactors, but revert to `"error"` before merging.

---

## CI: fail the build on type errors

**GitHub Actions step** (excerpt):
```yaml
- name: Type Check Services
  run: |
    python -m pyright backend/app/services/ --outputjson | jq -e '.summary.errorCount == 0'
```

`-e` makes `jq` return non‑zero when the expression is false, causing the step to fail.

---

## Pre-commit hooks

`.pre-commit-config.yaml` (excerpt):
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.8
    hooks:
      - id: ruff
        args: [--select, I, --fix]  # import sort only
  - repo: local
    hooks:
      - id: pyright-services
        name: Type check services
        entry: python -m pyright backend/app/services/
        language: system
        pass_filenames: false
      - id: check-future-annotations
        name: Enforce future annotations
        entry: bash -c "! grep -L "from __future__ import annotations" -R backend/app/services/"
        language: system
        pass_filenames: false
      - id: check-default-scaffolding
        name: Enforce default scaffolding
        entry: python backend/scripts/add_default_scaffolding.py --validate-only
        language: system
        pass_filenames: false
```

---

## Review checklist (copy into PR template)

- [ ] `from __future__ import annotations` at top of new/changed files
- [ ] `import logging` and `logger = logging.getLogger(__name__)` present
- [ ] No mutable default arguments (`[]`, `{}`)
- [ ] Nullable defaults use `Optional[...] = None` and are normalized
- [ ] No bare generics; all containers have element types
- [ ] Params use `Iterable[...]`/`Mapping[...]` where applicable; returns are concrete
- [ ] Public payloads use `TypedDict`/Pydantic; internals don't leak `Any`
- [ ] All functions have explicit return types (`-> None` allowed)
- [ ] SQLAlchemy 2.x: `Mapped[...]` columns; queries use `.scalars()`; return types annotated
- [ ] Pyright passes locally and in CI
- [ ] Default scaffolding validation passes

---

## Common failure translations

- **"Type of parameter X is partially unknown / list[Unknown]"**  
  Add element type. If default is `None`, make it `Optional[...]` and normalize.

- **"Expected type arguments for generic class 'list'/'Dict'"**  
  Replace bare generic with a concrete one (`list[str]`, `dict[str, int]`).

- **"Expression of type 'None' cannot be assigned to parameter 'list[...]'"**  
  Your signature isn't `Optional[...] = None` or you didn't normalize before use.

- **"Return type … is partially unknown"**  
  Give the function a concrete return type (`TypedDict`, `dict[str, T]`).

---

## FAQ

**Q: Can I use `| None` instead of `Optional[...]`?**  
A: Yes, `str | None` is equivalent and preferred in 3.10+. Be consistent within a file.

**Q: When do I pick Pydantic over `TypedDict`?**  
A: Use Pydantic for validation/defaults/serialization; `TypedDict` for static typing only.

**Q: Do I have to annotate private helpers?**  
A: Yes—errors often originate in helpers. Keep the same discipline throughout.

**Q: What if I don't need logging in a file?**  
A: Still include the scaffolding. It's lightweight and ensures consistency. You can use `logger.debug()` for development debugging.

**Q: Can I customize the logger name?**  
A: No. Always use `logger = logging.getLogger(__name__)` for consistency and proper log hierarchy.

---

## Project reference

This document is the **project standard** for all backend Python in this repo. It is referenced from:

- [README.md](../README.md) — "Standards" section
- [.cursor/rules/typing-standards.mdc](../.cursor/rules/typing-standards.mdc) — Cursor rule for `backend/**/*.py`
- [pyrightconfig.json](../pyrightconfig.json) — strict type checking (run `pyright backend/app` to validate)
