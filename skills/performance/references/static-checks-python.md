# Static Performance Anti-Pattern Catalog — Python

> SSOT: based on the §10.1 preliminary research from the spec (2026-06). Source URLs and licenses are cited.
> **Runtime tools are marked "verification delegated"** — static detection surfaces candidates, and the runtime tool renders the final verdict.

---

## 1. N+1 Query Detection

### Django

| Detection pattern | Correct form | Tool | Source |
|---|---|---|---|
| `for obj in qs: obj.related_set.all()` — reverse-relation access inside a loop | `prefetch_related('related_set')` | nplusone (MIT) | https://github.com/jmcarp/nplusone |
| `for obj in qs: obj.fk_field.attr` — forward foreign-key access inside a loop | `select_related('fk_field')` | nplusone / django-zen-queries | https://github.com/dabapps/django-zen-queries (BSD-2) |
| Modern fork (supports Django 5.x) | — | nplus1 | https://github.com/huynguyengl99/nplus1 |

**Static flagging command** (files containing both a `for` loop and an ORM-access call — a whole-file
co-occurrence check, not proof the access is inside the loop body; always confirm by reading the file):

```bash
# Safe intersection — avoids piping grep's "file:line:text" output into xargs (which splits on the
# embedded spaces and breaks). List files matching each pattern separately, then intersect.
comm -12 \
  <(grep -rl "for .*:" src/ | sort) \
  <(grep -rl "\.objects\.\(get\|filter\|all\)(" src/ | sort)
```

**Verification delegated**: wiring `nplusone.hooks.NPlusOneHook` into your tests catches runtime N+1 as an exception.

### SQLAlchemy

| Detection pattern | Correct form | Source |
|---|---|---|
| Lazy load inside a loop (default `lazy='select'`) | `joinedload()` / `selectinload()` | https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html (MIT) |
| Repeated `Session.get()` in a loop | Batch fetch or an `in_()` filter | Same as above |

## 2. Static Complexity Aid — radon (Python-specific)

| Tool | License | Source |
|---|---|---|
| radon | MIT | https://radon.readthedocs.io/ |

```bash
radon cc src/ -s -a   # cyclomatic complexity per function, sorted, with average
```

> For language-agnostic nested-loop/recursion detection and runtime profilers, see
> [`static-checks-complexity.md`](static-checks-complexity.md) (lizard-based).
