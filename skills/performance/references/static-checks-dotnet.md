# Static Performance Anti-Pattern Catalog — .NET / EF Core

> SSOT: based on the §10.1 preliminary research from the spec (2026-06). Source URLs and licenses are cited.

---

## N+1 Query Detection

| Detection pattern | Correct form | Source |
|---|---|---|
| `foreach (var x in ctx.Entities) { x.Nav.Load(); }` | `.Include(e => e.Nav)` | https://learn.microsoft.com/en-us/ef/core/performance/efficient-querying (MIT) |
| Overusing `.Include()` chains on large result sets | Consider a split query (`AsSplitQuery()`) | https://learn.microsoft.com/en-us/ef/core/querying/single-split-queries |

> For language-agnostic nested-loop/recursion detection and runtime profilers, see
> [`static-checks-complexity.md`](static-checks-complexity.md).
