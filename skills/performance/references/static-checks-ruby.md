# Static Performance Anti-Pattern Catalog — Ruby / Rails

> SSOT: based on the §10.1 preliminary research from the spec (2026-06). Source URLs and licenses are cited.

---

## N+1 Query Detection

| Detection pattern | Correct form | Tool | Source |
|---|---|---|---|
| `belongs_to` / `has_many` access inside a loop (lazy) | `includes(:assoc)` / `eager_load(:assoc)` | bullet (MIT) | https://github.com/flyerhzm/bullet (MIT) |
| Association access inside a loop after `where` | Use `preload` | prosopite (Apache-2.0) | https://github.com/charkost/prosopite |

**Verification delegated**: enabling the `bullet` gem in the test environment logs N+1 and unused eager loading.

> For language-agnostic nested-loop/recursion detection and runtime profilers, see
> [`static-checks-complexity.md`](static-checks-complexity.md).
