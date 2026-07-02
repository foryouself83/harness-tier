# Static Performance Anti-Pattern Catalog

> SSOT: based on the §10.1–§10.4 preliminary research from the spec (2026-06). Source URLs and licenses are cited.
> **Runtime tools are marked "verification delegated"** — static detection surfaces candidates, and the runtime tool renders the final verdict.

---

## 1. N+1 Query Detection

### Python / Django

| Detection pattern | Correct form | Tool | Source |
|---|---|---|---|
| `for obj in qs: obj.related_set.all()` — reverse-relation access inside a loop | `prefetch_related('related_set')` | nplusone (MIT) | https://github.com/jmcarp/nplusone |
| `for obj in qs: obj.fk_field.attr` — forward foreign-key access inside a loop | `select_related('fk_field')` | nplusone / django-zen-queries | https://github.com/dabapps/django-zen-queries (BSD-2) |
| Modern fork (supports Django 5.x) | — | nplus1 | https://github.com/huynguyengl99/nplus1 |

Static flagging heuristic: grep for `.objects.get()`, `.objects.filter()`, and `.all()` patterns inside a `for` block.
**Verification delegated**: wiring `nplusone.hooks.NPlusOneHook` into your tests catches runtime N+1 as an exception.

### SQLAlchemy (Python ORM)

| Detection pattern | Correct form | Source |
|---|---|---|
| Lazy load inside a loop (default `lazy='select'`) | `joinedload()` / `selectinload()` | https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html (MIT) |
| Repeated `Session.get()` in a loop | Batch fetch or an `in_()` filter | Same as above |

### Java / Hibernate

| Detection pattern | Correct form | Tool | Source |
|---|---|---|---|
| `@OneToMany` default `FetchType.LAZY` + loop access | `FetchType.EAGER` or `JOIN FETCH` JPQL | Hibernate Statistics (runtime verification delegated) | https://docs.jboss.org/hibernate/orm/5.4/javadocs/org/hibernate/stat/Statistics.html |
| `entityManager.find()` inside a loop | `entityManager.createQuery("...JOIN FETCH...")` | — | Same as above |

**Verification delegated**: after `hibernate.generate_statistics=true`, measure the queries per loop with `StatisticsImpl.getQueryExecutionCount()`.

### Ruby / Rails

| Detection pattern | Correct form | Tool | Source |
|---|---|---|---|
| `belongs_to` / `has_many` access inside a loop (lazy) | `includes(:assoc)` / `eager_load(:assoc)` | bullet (MIT) | https://github.com/flyerhzm/bullet (MIT) |
| Association access inside a loop after `where` | Use `preload` | prosopite (Apache-2.0) | https://github.com/charkost/prosopite |

**Verification delegated**: enabling the `bullet` gem in the test environment logs N+1 and unused eager loading.

### .NET / EF Core

| Detection pattern | Correct form | Source |
|---|---|---|
| `foreach (var x in ctx.Entities) { x.Nav.Load(); }` | `.Include(e => e.Nav)` | https://learn.microsoft.com/en-us/ef/core/performance/efficient-querying (MIT) |
| Overusing `.Include()` chains on large result sets | Consider a split query (`AsSplitQuery()`) | https://learn.microsoft.com/en-us/ef/core/querying/single-split-queries |

### Prisma (Node.js)

| Detection pattern | Correct form | Source |
|---|---|---|
| `for (const u of users) { await prisma.post.findMany({ where: { userId: u.id } }) }` | `include: { posts: true }` or batch with `prisma.$transaction` | https://www.prisma.io/docs/orm/prisma-client/queries/query-optimization-performance (Apache-2.0) |

### TypeORM (Node.js)

| Detection pattern | Correct form | Source |
|---|---|---|
| `@ManyToOne` default lazy + loop access | `eager: true` or `QueryBuilder.leftJoinAndSelect()` | https://typeorm.io/docs/relations/eager-and-lazy-relations/ (MIT) |

---

## 2. DB Query-Plan Caution Patterns

> Flag only patterns that are statically detectable. The final verdict is delegated to running EXPLAIN ANALYZE.

| Static pattern | Problem | Recommendation | Verification command |
|---|---|---|---|
| `SELECT *` | Transfers unneeded columns, loses index coverage | Specify only the needed columns | Check the plan after `EXPLAIN ANALYZE SELECT *` |
| `WHERE func(column) = ?` | Function wrapping prevents an index scan | Rewrite without the function, or use a function-based index | `EXPLAIN ANALYZE` |
| `LIKE '%keyword%'` | Leading wildcard forces a full scan | Consider a reverse index or FTS | `EXPLAIN ANALYZE` |
| Complex `OR` chains | The optimizer may fail to merge indexes | Consider rewriting as `UNION ALL` | `EXPLAIN ANALYZE` |
| Overusing subquery `IN (SELECT ...)` | Correlated subqueries can cause N×M scans | Rewrite as `JOIN` or `EXISTS` | `EXPLAIN ANALYZE` |

### EXPLAIN Official Docs

| DB | Command | Source |
|---|---|---|
| PostgreSQL | `EXPLAIN (ANALYZE, BUFFERS)` | https://www.postgresql.org/docs/current/sql-explain.html · https://www.postgresql.org/docs/current/using-explain.html |
| MySQL 8.4 | `EXPLAIN FORMAT=JSON` | https://dev.mysql.com/doc/refman/8.4/en/explain.html · https://dev.mysql.com/doc/refman/8.4/en/explain-output.html |
| SQLite | `EXPLAIN QUERY PLAN` | https://www.sqlite.org/eqp.html |

### Supplementary Resources

- **Use The Index, Luke!** (guide to interpreting query plans): https://use-the-index-luke.com/sql/explain-plan
- **PEV2** (PostgreSQL EXPLAIN visualization, PostgreSQL License): https://github.com/dalibo/pev2

---

## 3. Profiling / Complexity

> **Important**: Cyclomatic complexity (CC) is a count of branches, **not Big-O time complexity**.
> A high CC can still be O(n), and a low CC can still be O(n²). Do not conflate the two concepts.

### Static Complexity Aids (detection aids — not runtime verification)

| Tool | Supported languages | License | Source |
|---|---|---|---|
| lizard | Python, C/C++, Java, JS, and more | MIT | https://github.com/terryyin/lizard |
| radon | Python | MIT | https://radon.readthedocs.io/ |

lizard usage example:
```bash
lizard src/ -C 10  # Report functions with cyclomatic complexity over 10
```

> The output is a "list of functions with high CC" and is not evidence of algorithmic complexity.
> Supplement it with a separate grep for nested loops or recursion patterns.

### Static Detection Heuristics for Nested Loops / Recursion

```bash
# Three or more levels of nested for (Python example)
grep -Pn "^(\s{4})+for " src/**/*.py | awk -F: '{print $2, $1}' | sort -rn | head -20

# Recursive functions (a function calls itself inside its own body)
grep -Pn "def (\w+).*:\n.*\1(" src/**/*.py  # Simple heuristic; needs cross-checking
```

### Runtime Profilers (verification delegated)

| Language | Tool | License | Source |
|---|---|---|---|
| Python | py-spy | MIT | https://github.com/benfred/py-spy |
| Python | cProfile (built-in) | PSF | https://docs.python.org/3/library/profile.html |
| Python | Scalene | Apache-2.0 | https://github.com/plasma-umass/scalene |
| Node.js | --prof (built-in V8) | MIT (Node) | https://nodejs.org/learn/getting-started/profiling |
| Node.js | 0x | MIT | https://github.com/davidmarkclements/0x |
| Node.js | Clinic.js | MIT *(note: maintenance inactive)* | https://github.com/clinicjs/node-clinic |
| Go | runtime/pprof (built-in) | BSD-3 | https://pkg.go.dev/runtime/pprof |
| Go | net/http/pprof (built-in) | BSD-3 | https://pkg.go.dev/net/http/pprof |
| Java | async-profiler | Apache-2.0 | https://github.com/async-profiler/async-profiler |
| Java | JDK Flight Recorder (JFR) | GPL+CE | https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html |

---

## 4. Frontend Re-renders (React)

### When React Compiler v1.0 Is Active (as of the 2025-10 GA)

**Detect whether the Compiler is active first** — check for `babel-plugin-react-compiler` / `@babel/plugin-react-compiler` /
the Vite `reactCompiler` plugin.

When the Compiler is active, **automatic memoization** applies, so relax the manual `memo`/`useMemo`/`useCallback`
rules. Instead, focus checks on **Rules of React violations**:

- The `rules-of-hooks` + `exhaustive-deps` rules of `eslint-plugin-react-hooks` (integrated with the Compiler)
- Rules of React violations such as calling hooks outside a component or calling hooks conditionally

| Item | Source |
|---|---|
| eslint-plugin-react-hooks (MIT) | https://react.dev/reference/eslint-plugin-react-hooks |
| React Compiler v1.0 blog | https://react.dev/blog/2025/10/07/react-compiler-1 |
| React Compiler introduction | https://react.dev/learn/react-compiler/introduction |

### When React Compiler Is Inactive

| Static detection pattern | Problem | Recommendation | Source |
|---|---|---|---|
| Inline object in a JSX prop `<Comp style={{ color: 'red' }}>` | A new object reference every render → child re-renders | Memoize with `useMemo` or extract to a module constant | https://react.dev/reference/react/useMemo |
| Inline function in a JSX prop `<Comp onClick={() => handler(id)}>` | A new function reference every render | `useCallback(…, [id])` | https://react.dev/reference/react/useCallback |
| Inline prop on a `React.memo`-wrapped component | The memo is invalidated | Give the prop a stable reference | https://react.dev/reference/react/memo |
| Missing or excessive `useEffect` deps array | Stale closure / infinite loop | Apply the `exhaustive-deps` lint rule | https://react.dev/reference/eslint-plugin-react-hooks |

### Runtime Re-render Tools (verification delegated)

| Tool | License | Source |
|---|---|---|
| React DevTools Profiler | MIT | https://react.dev/reference/react/Profiler |
| why-did-you-render | MIT | https://github.com/welldone-software/why-did-you-render |
| react-scan | MIT | https://github.com/aidenybai/react-scan |
