# Static Performance Anti-Pattern Catalog — Java / Hibernate

> SSOT: based on the §10.1 preliminary research from the spec (2026-06). Source URLs and licenses are cited.

---

## N+1 Query Detection

| Detection pattern | Correct form | Tool | Source |
|---|---|---|---|
| `@OneToMany` default `FetchType.LAZY` + loop access | `FetchType.EAGER` or `JOIN FETCH` JPQL | Hibernate Statistics (runtime verification delegated) | https://docs.jboss.org/hibernate/orm/5.4/javadocs/org/hibernate/stat/Statistics.html |
| `entityManager.find()` inside a loop | `entityManager.createQuery("...JOIN FETCH...")` | — | Same as above |

**Verification delegated**: after `hibernate.generate_statistics=true`, measure the queries per loop with `StatisticsImpl.getQueryExecutionCount()`.

> For language-agnostic nested-loop/recursion detection and runtime profilers (async-profiler, JFR), see
> [`static-checks-complexity.md`](static-checks-complexity.md).
