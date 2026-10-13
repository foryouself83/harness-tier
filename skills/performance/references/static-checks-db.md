# DB Query-Plan Caution Patterns (language-agnostic)

> SSOT: based on the §10.2 preliminary research from the spec (2026-06). Source URLs and licenses are cited.
> Flag only patterns that are statically detectable. The final verdict is delegated to running EXPLAIN ANALYZE.

---

## 1. Static Patterns

| Static pattern | Problem | Recommendation | Verification command |
|---|---|---|---|
| `SELECT *` | Transfers unneeded columns, loses index coverage | Specify only the needed columns | Check the plan after `EXPLAIN ANALYZE SELECT *` |
| `WHERE func(column) = ?` | Function wrapping prevents an index scan | Rewrite without the function, or use a function-based index | `EXPLAIN ANALYZE` |
| `LIKE '%keyword%'` | Leading wildcard forces a full scan | Consider a reverse index or FTS | `EXPLAIN ANALYZE` |
| Complex `OR` chains | The optimizer may fail to merge indexes | Consider rewriting as `UNION ALL` | `EXPLAIN ANALYZE` |
| Overusing subquery `IN (SELECT ...)` | Correlated subqueries can cause N×M scans | Rewrite as `JOIN` or `EXISTS` | `EXPLAIN ANALYZE` |

## 2. EXPLAIN Official Docs

| DB | Command | Source |
|---|---|---|
| PostgreSQL | `EXPLAIN (ANALYZE, BUFFERS)` | https://www.postgresql.org/docs/current/sql-explain.html · https://www.postgresql.org/docs/current/using-explain.html |
| MySQL 8.4 | `EXPLAIN FORMAT=JSON` | https://dev.mysql.com/doc/refman/8.4/en/explain.html · https://dev.mysql.com/doc/refman/8.4/en/explain-output.html |
| SQLite | `EXPLAIN QUERY PLAN` | https://www.sqlite.org/eqp.html |

## 3. Supplementary Resources

- **Use The Index, Luke!** (guide to interpreting query plans): https://use-the-index-luke.com/sql/explain-plan
- **PEV2** (PostgreSQL EXPLAIN visualization, PostgreSQL License): https://github.com/dalibo/pev2
