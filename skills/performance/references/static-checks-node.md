# Static Performance Anti-Pattern Catalog — Node.js (Prisma / TypeORM)

> SSOT: based on the §10.1 preliminary research from the spec (2026-06). Source URLs and licenses are cited.

---

## N+1 Query Detection

### Prisma

| Detection pattern | Correct form | Source |
|---|---|---|
| `for (const u of users) { await prisma.post.findMany({ where: { userId: u.id } }) }` | `include: { posts: true }` or batch with `prisma.$transaction` | https://www.prisma.io/docs/orm/prisma-client/queries/query-optimization-performance (Apache-2.0) |

### TypeORM

| Detection pattern | Correct form | Source |
|---|---|---|
| `@ManyToOne` default lazy + loop access | `eager: true` or `QueryBuilder.leftJoinAndSelect()` | https://typeorm.io/docs/relations/eager-and-lazy-relations/ (MIT) |

> For language-agnostic nested-loop/recursion detection and runtime profilers (--prof, 0x, Clinic.js), see
> [`static-checks-complexity.md`](static-checks-complexity.md).
