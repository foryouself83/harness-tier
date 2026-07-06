# performance/integration 스킬 버그 수정 + 언어별 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/code-review`로 발견한 `skills/performance`·`skills/integration`의 11개 CONFIRMED 버그를 모두 고치고, `static-checks.md`를 언어/도구 축으로 재구성하며, Electron을 통합 스킬의 독립 3번째 분기로 승격시킨다.

**Architecture:** performance는 `SKILL.md`를 얇은 디스패처로 남기고 `references/static-checks-{python,java,ruby,dotnet,node,react,db,complexity}.md` 8개 파일로 분리한다. integration은 기존 web/non-web 2분기에 `references/electron.md`를 SSOT로 하는 독립 Electron 분기(`## 4`)를 추가하고, 이후 섹션 번호를 한 칸씩 민다.

**Tech Stack:** Markdown 스킬 파일(bash/node 스니펫 포함), lizard(정적 복잡도), openapi-to-k6+k6, Playwright.

**Design spec:** `docs/superpowers/specs/2026-07-06-performance-integration-skill-fixes-design.md`

## Global Constraints

- 모든 새 파일은 기존 스킬 파일들과 동일한 마크다운 스타일(SSOT 각주, 소스 URL, 라이선스 표기)을 따른다.
- 모든 grep/find 예시 명령은 실제로 실행해 동작을 검증한 뒤 문서에 반영한다 (거짓 주장 재발 방지).
- 기존 파일에서 옮겨지는 표 내용(라이선스·URL·detection pattern)은 문구를 바꾸지 않고 그대로 옮긴다 — 새로 지어내지 않는다.
- `SKILL.md`의 `§` 상호참조 번호는 섹션이 추가/이동될 때마다 반드시 함께 갱신한다.

---

## Task 1: `static-checks-db.md` + `static-checks-complexity.md` (언어 무관 공유 파일)

**Files:**
- Create: `skills/performance/references/static-checks-db.md`
- Create: `skills/performance/references/static-checks-complexity.md`
- Test: 수동 bash 검증 (아래 스텝 참고, 별도 테스트 파일 없음)

**Interfaces:**
- Produces: `static-checks-db.md`(DB 쿼리플랜 SSOT), `static-checks-complexity.md`(lizard 기반 복잡도 SSOT) — Task 9(SKILL.md 재작성)에서 이 두 파일을 참조.

- [ ] **Step 1: `static-checks-db.md` 작성 — 원본 §2를 그대로 이동**

`skills/performance/references/static-checks.md`의 "## 2. DB Query-Plan Caution Patterns" 섹션(원본 라인 67-91)을 아래와 같이 옮긴다 (내용 변경 없음, 헤더만 `## 1.`로 재번호):

```markdown
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
```

- [ ] **Step 2: Verify `static-checks-db.md` — before/after grep check**

Run (expected FAIL — file does not exist yet if Step 1 hasn't run):
```bash
grep -c "EXPLAIN ANALYZE" skills/performance/references/static-checks-db.md
```
Expected after Step 1: `5` (five occurrences). If it doesn't match, re-check Step 1's content was written exactly.

- [ ] **Step 3: `static-checks-complexity.md` 작성 — lizard로 nested-loop/recursion grep 교체**

버그가 확인된 원본 §3(라인 94-137)의 `grep -Pn "^(\s{4})+for "`와 `grep -Pn "def (\w+).*:\n.*\1("` 휴리스틱을 폐기하고 lizard 기반으로 교체한다:

```markdown
# Static Complexity Detection (language-agnostic)

> SSOT: based on the §10.3 preliminary research from the spec (2026-06). Source URLs and licenses are cited.
> **Runtime tools are marked "verification delegated"** — static detection surfaces candidates, and the runtime tool renders the final verdict.

---

## 1. Cyclomatic Complexity vs. Algorithmic Complexity

> **Important**: Cyclomatic complexity (CC) is a count of branches, **not Big-O time complexity**.
> A high CC can still be O(n), and a low CC can still be O(n²). Do not conflate the two concepts.

## 2. Nested-Loop / Recursion Detection — lizard (language-agnostic)

> **Why lizard instead of grep**: a hand-rolled grep heuristic for "3+ nested loops" or "recursive function" is
> fragile and was previously broken in this catalog — it silently no-ops on `**` without `shopt -s globstar`,
> misdetects depth on non-4-space indentation (tabs, 2-space), and a `\n`-embedded `-P` pattern can never match
> across two lines without `-z`/`--null-data` (GNU grep matches per-line). lizard parses each language's real
> token structure and reports nesting/complexity independent of indentation style or line-wrapping, with one
> command that works the same way across every detected stack.

| Tool | Supported languages | License | Source |
|---|---|---|---|
| lizard | Python, C/C++, Java, JS/TS, C#, Ruby, Go, and more | MIT | https://github.com/terryyin/lizard |

**Installation** (if missing):
```bash
pip install lizard   # or: pipx install lizard
```

**Usage — flag high cyclomatic complexity and long functions**:
```bash
lizard src/ -C 10          # functions with cyclomatic complexity > 10
lizard src/ -L 50          # functions longer than 50 lines (a nesting/complexity proxy)
```

**Usage — machine-readable output for filtering by nesting depth or CC**:
```bash
lizard src/ --xml > /tmp/lizard-report.xml
```

> lizard's output is a list of functions with high CC/NLOC — still not proof of O(n²)+ time complexity, and it
> does not itself flag unbounded recursion. **Verification delegated**: hand off flagged functions to a runtime
> profiler (below) to confirm actual behavior under realistic input sizes.

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
```

- [ ] **Step 4: Reproduce the old bug, then prove lizard doesn't have it**

Build a fixture with 4-level nesting and tab indentation (the exact case that broke the old `\s{4}` grep):
```bash
mkdir -p /tmp/harness-perf-fixture/src
printf 'def f():\n\tfor a in x:\n\t\tfor b in y:\n\t\t\tfor c in z:\n\t\t\t\tfor d in w:\n\t\t\t\t\tpass\n' > /tmp/harness-perf-fixture/src/nested.py
```
Reproduce the old broken behavior (expected: **no output** — this is the bug):
```bash
grep -Pn "^(\s{4})+for " /tmp/harness-perf-fixture/src/nested.py
```
Now run lizard (install if missing) and confirm it reports the function with NLOC/CC data regardless of tabs:
```bash
pip install --quiet lizard 2>/dev/null; lizard /tmp/harness-perf-fixture/src -C 1
```
Expected: a row for function `f` is printed (lizard is indentation-agnostic — it parses Python's actual block structure, not whitespace-width). Clean up:
```bash
rm -rf /tmp/harness-perf-fixture
```

- [ ] **Step 5: Commit**

```bash
git add skills/performance/references/static-checks-db.md skills/performance/references/static-checks-complexity.md
git commit -m "feat(performance): split DB query-plan and complexity checks into shared reference files, replace broken nested-loop/recursion grep with lizard"
```

---

## Task 2: `static-checks-python.md` (N+1: Django + SQLAlchemy, N+1 xargs fix, + radon)

**Files:**
- Create: `skills/performance/references/static-checks-python.md`

**Interfaces:**
- Produces: `static-checks-python.md` — referenced by Task 9's SKILL.md dispatcher when Python is detected.

- [ ] **Step 1: Reproduce the confirmed xargs bug**

```bash
mkdir -p /tmp/harness-py-fixture/src
cat > /tmp/harness-py-fixture/src/views.py <<'EOF'
def bad(queryset):
    for obj in queryset:
        obj.related_set.all()
EOF
```
Reproduce the bug (expected: `grep: for: No such file or directory` errors, NOT the filename):
```bash
grep -rn "for .*:" /tmp/harness-py-fixture/src/ | xargs grep -l "\.objects\.\(get\|filter\|all\)()" 2>&1
```

- [ ] **Step 2: Write and verify the fixed detection command**

```bash
comm -12 \
  <(grep -rl "for .*:" /tmp/harness-py-fixture/src/ | sort) \
  <(grep -rl "\.related_set\.\|\.objects\.\(get\|filter\|all\)()" /tmp/harness-py-fixture/src/ | sort)
```
Expected: `/tmp/harness-py-fixture/src/views.py` printed exactly once (no xargs errors). Clean up:
```bash
rm -rf /tmp/harness-py-fixture
```

- [ ] **Step 3: Write `static-checks-python.md`**

```markdown
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
  <(grep -rl "\.objects\.\(get\|filter\|all\)()" src/ | sort)
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
```

- [ ] **Step 4: Commit**

```bash
git add skills/performance/references/static-checks-python.md
git commit -m "feat(performance): add static-checks-python.md, fix N+1 xargs pipe bug via comm -12"
```

---

## Task 3: `static-checks-java.md` · `static-checks-ruby.md` · `static-checks-dotnet.md` · `static-checks-node.md`

**Files:**
- Create: `skills/performance/references/static-checks-java.md`
- Create: `skills/performance/references/static-checks-ruby.md`
- Create: `skills/performance/references/static-checks-dotnet.md`
- Create: `skills/performance/references/static-checks-node.md`

**Interfaces:**
- Produces: four per-stack N+1 reference files, no new bugs to fix here (content moved verbatim from the original `static-checks.md`, only the xargs-based detection command pattern — if any stack copies performance/SKILL.md's broken command style — is replaced with the same `comm -12` pattern from Task 2).

- [ ] **Step 1: `static-checks-java.md`**

```markdown
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
```

- [ ] **Step 2: `static-checks-ruby.md`**

```markdown
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
```

- [ ] **Step 3: `static-checks-dotnet.md`**

```markdown
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
```

- [ ] **Step 4: `static-checks-node.md`**

```markdown
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
```

- [ ] **Step 5: Verify all four files exist and link correctly**

```bash
for f in java ruby dotnet node; do
  grep -l "static-checks-complexity.md" "skills/performance/references/static-checks-$f.md" || echo "MISSING LINK: $f"
done
```
Expected: no `MISSING LINK` lines printed.

- [ ] **Step 6: Commit**

```bash
git add skills/performance/references/static-checks-java.md skills/performance/references/static-checks-ruby.md skills/performance/references/static-checks-dotnet.md skills/performance/references/static-checks-node.md
git commit -m "feat(performance): split Java/Ruby/.NET/Node N+1 catalogs into per-language reference files"
```

---

## Task 4: `static-checks-react.md` (Frontend re-renders, fix React Compiler detection regex)

**Files:**
- Create: `skills/performance/references/static-checks-react.md`

**Interfaces:**
- Produces: `static-checks-react.md` (with the fixed React Compiler detection command) — Task 9's SKILL.md §2.4 will point here.

- [ ] **Step 1: Reproduce the confirmed regex bug**

```bash
mkdir -p /tmp/harness-react-fixture
cat > /tmp/harness-react-fixture/vite.config.ts <<'EOF'
export default {
  plugins: [react({ babel: { plugins: [] } })],
  reactCompiler: true,
};
EOF
```
Reproduce the bug (expected: **no output** — the old regex misses camelCase `reactCompiler`):
```bash
grep -r "react-compiler\|babel-plugin-react-compiler" /tmp/harness-react-fixture/vite.config.ts
```

- [ ] **Step 2: Write and verify the fixed detection command**

```bash
grep -riE "react-compiler|babel-plugin-react-compiler|reactCompiler" /tmp/harness-react-fixture/vite.config.ts
```
Expected: the `reactCompiler: true;` line is printed. Clean up:
```bash
rm -rf /tmp/harness-react-fixture
```

- [ ] **Step 3: Write `static-checks-react.md`**

```markdown
# Static Performance Anti-Pattern Catalog — React (Frontend Re-renders)

> SSOT: based on the §10.4 preliminary research from the spec (2026-06). Source URLs and licenses are cited.

---

## 1. Detect Whether React Compiler v1.0 Is Active (as of the 2025-10 GA)

**Detect first** — check for `babel-plugin-react-compiler` / `@babel/plugin-react-compiler` / the Vite
`reactCompiler` option (camelCase, no hyphen — a plain `react-compiler` string match misses this):

```bash
grep -riE "react-compiler|babel-plugin-react-compiler|reactCompiler" package.json babel.config.* vite.config.* 2>/dev/null
```

| State | Applicable rule |
|---|---|
| **Compiler active** | Relax the manual `memo`/`useMemo`/`useCallback` rules. Instead, focus checks on **Rules of React violations** (`eslint-plugin-react-hooks`). |
| **Compiler inactive** | Statically detect inline object/function props, missing `useCallback`, unnecessary `React.createElement` re-creation, etc. |

## 2. When React Compiler Is Active

- The `rules-of-hooks` + `exhaustive-deps` rules of `eslint-plugin-react-hooks` (integrated with the Compiler)
- Rules of React violations such as calling hooks outside a component or calling hooks conditionally

| Item | Source |
|---|---|
| eslint-plugin-react-hooks (MIT) | https://react.dev/reference/eslint-plugin-react-hooks |
| React Compiler v1.0 blog | https://react.dev/blog/2025/10/07/react-compiler-1 |
| React Compiler introduction | https://react.dev/learn/react-compiler/introduction |

## 3. When React Compiler Is Inactive

| Static detection pattern | Problem | Recommendation | Source |
|---|---|---|---|
| Inline object in a JSX prop `<Comp style={{ color: 'red' }}>` | A new object reference every render → child re-renders | Memoize with `useMemo` or extract to a module constant | https://react.dev/reference/react/useMemo |
| Inline function in a JSX prop `<Comp onClick={() => handler(id)}>` | A new function reference every render | `useCallback(…, [id])` | https://react.dev/reference/react/useCallback |
| Inline prop on a `React.memo`-wrapped component | The memo is invalidated | Give the prop a stable reference | https://react.dev/reference/react/memo |
| Missing or excessive `useEffect` deps array | Stale closure / infinite loop | Apply the `exhaustive-deps` lint rule | https://react.dev/reference/eslint-plugin-react-hooks |

## 4. Runtime Re-render Tools (verification delegated)

| Tool | License | Source |
|---|---|---|
| React DevTools Profiler | MIT | https://react.dev/reference/react/Profiler |
| why-did-you-render | MIT | https://github.com/welldone-software/why-did-you-render |
| react-scan | MIT | https://github.com/aidenybai/react-scan |
```

- [ ] **Step 4: Commit**

```bash
git add skills/performance/references/static-checks-react.md
git commit -m "feat(performance): add static-checks-react.md, fix reactCompiler camelCase detection gap"
```

---

## Task 5: Delete old `static-checks.md`, verify no dangling references remain

**Files:**
- Delete: `skills/performance/references/static-checks.md`

**Interfaces:**
- Consumes: Tasks 1-4 (all 8 replacement files must exist first).

- [ ] **Step 1: Confirm all 8 replacement files exist before deleting**

```bash
for f in db complexity python java ruby dotnet node react; do
  test -f "skills/performance/references/static-checks-$f.md" || echo "MISSING: $f"
done
```
Expected: no output. If anything is missing, stop and complete the corresponding earlier task first.

- [ ] **Step 2: Delete the old file**

```bash
git rm skills/performance/references/static-checks.md
```

- [ ] **Step 3: Verify nothing else in the repo still references the deleted file**

```bash
grep -rn "static-checks.md" skills/ | grep -v "static-checks-"
```
Expected: no output (Task 9 will update `SKILL.md`'s references before this task's commit lands — if this task runs before Task 9, expect hits in `performance/SKILL.md` and note them; re-run this check after Task 9 completes to confirm zero).

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(performance): remove static-checks.md, superseded by per-stack reference files"
```

---

## Task 6: Rewrite `performance/SKILL.md` (dispatcher, host-doc merge rule, BASE_URL delegation, remove broken inline examples)

**Files:**
- Modify: `skills/performance/SKILL.md` (full rewrite of §1, §2, §3.1-3.2)

**Interfaces:**
- Consumes: `static-checks-{python,java,ruby,dotnet,node,react,db,complexity}.md` (Tasks 1-4), `api-load.md` (Task 7 — written after this task, but referenced by name/section here; if Task 7 hasn't landed yet, the cross-reference is still valid since api-load.md already exists and will be edited in place).

- [ ] **Step 1: Reproduce the confirmed host-doc partial-coverage gap**

Confirm today's §1 text has no merge instruction (expected: match found, confirming the gap exists before the fix):
```bash
grep -n "run only the sections for those stacks" skills/performance/SKILL.md
```

- [ ] **Step 2: Rewrite §1 "Stack Detection" with the partial-coverage merge rule**

Replace the current §1 body (lines 19-45) with:

```markdown
## 1. Stack Detection

First consume the host documentation; if none exists, fall back to the built-in catalog.

```bash
# Check for documentation generated by the host harness-researcher (Phase 4; consume first if present)
ls docs/verification/performance.md 2>/dev/null && cat docs/verification/performance.md
```

- **If `docs/verification/performance.md` exists**: read the stack list, SSOT, and tools from the file and
  run those sections. **Also independently run Automatic Stack Detection (below)** — for any detected stack
  that the host doc does NOT mention, run that stack's fallback reference file too (the host doc may be
  stale or predate a newly added stack; do not silently skip undocumented stacks).
- **If `docs/verification/performance.md` is absent**: fall back entirely to Automatic Stack Detection.

### Automatic Stack Detection (fallback / gap-fill)

| Signal file/pattern | Detected stack | Reference file |
|---|---|---|
| `pyproject.toml` / `setup.py` / `*.py` | Python | [`static-checks-python.md`](references/static-checks-python.md) |
| `package.json` (ORM/express in `"dependencies"`) | Node.js | [`static-checks-node.md`](references/static-checks-node.md) |
| `package.json` (`react`/`next`) | React | [`static-checks-react.md`](references/static-checks-react.md) |
| `pom.xml` / `*.java` / `build.gradle` | Java/Hibernate | [`static-checks-java.md`](references/static-checks-java.md) |
| `Gemfile` / `*.rb` | Ruby | [`static-checks-ruby.md`](references/static-checks-ruby.md) |
| `*.csproj` / `*.cs` | .NET | [`static-checks-dotnet.md`](references/static-checks-dotnet.md) |
| `go.mod` / `*.go` | Go | (no dedicated N+1 catalog yet — run [`static-checks-complexity.md`](references/static-checks-complexity.md) only) |
| `*.sql` / DB-related migrations | DB | [`static-checks-db.md`](references/static-checks-db.md) |

If multiple stacks are detected, **run all of them**. Always also run
[`static-checks-complexity.md`](references/static-checks-complexity.md) (language-agnostic via lizard),
regardless of which stacks were detected.
```

- [ ] **Step 3: Rewrite §2 as a thin per-stack dispatcher**

Replace the current §2 body (lines 48-108, including the broken N+1 xargs example and the broken nested-loop
description) with:

```markdown
## 2. Language-Specific Static Anti-Pattern Flagging

> **Authoritative catalogs (SSOT)** — one file per stack, listed in the table in §1. Add/modify detection
> patterns only in the relevant `references/static-checks-<stack>.md` file, never here.

For each detected stack, open its reference file from §1's table and follow its detection commands and
verification-delegated runtime tools. Every stack file follows the same shape: a detection-pattern table,
the statically-safe grep/tool command, the correct fix, and the runtime tool to delegate final verification to.

DB query-plan caution patterns (`SELECT *`, function-wrapped `WHERE`, leading-wildcard `LIKE`, etc.) are
DB-engine-based, not language-based — always consult [`static-checks-db.md`](references/static-checks-db.md)
when a DB is present, regardless of the application language.
```

- [ ] **Step 4: Rewrite §3.1 to delegate BASE_URL entirely to `api-load.md`, removing the divergent duplicate**

Replace the current §3.1 body (lines 115-128, including the inline `curl` loop with no `-o` and the false
"same principle as playwright-scaffold" claim that pointed at a script which didn't implement it) with:

```markdown
### 3.1 Automatic OpenAPI Spec Discovery + BASE_URL Confirmation

> **The authoritative procedure = [`references/api-load.md`](references/api-load.md) §1** (candidate-path
> list, BASE_URL multi-source detection + **required user confirmation** via `AskUserQuestion`, and the
> ASP.NET variable-documentName handling). Follow it exactly — do not re-derive BASE_URL inline here.
```

- [ ] **Step 5: Remove the unused `WebFetch` permission from frontmatter**

Reproduce the confirmed gap — grep the whole skill directory and show `allowed-tools` is the only hit:
```bash
grep -rn "WebFetch" skills/performance/
```
Expected (before fix): exactly one match, `skills/performance/SKILL.md:4:allowed-tools: ...WebFetch` — no other
file or command in the skill actually invokes it.

Fix the frontmatter (line 4) from:
```
allowed-tools: Bash, Read, Grep, Glob, WebFetch
```
to:
```
allowed-tools: Bash, Read, Grep, Glob
```

Verify:
```bash
grep -rn "WebFetch" skills/performance/
```
Expected (after fix): no output.

- [ ] **Step 6: Verify the rewritten SKILL.md has no dangling reference to the deleted `static-checks.md`**

```bash
grep -n "static-checks.md" skills/performance/SKILL.md
```
Expected: no output (all references now point to `static-checks-<stack>.md` files).

- [ ] **Step 7: Verify every reference file named in the new §1 table actually exists**

```bash
for f in python node react java ruby dotnet db complexity; do
  test -f "skills/performance/references/static-checks-$f.md" || echo "DANGLING REF: $f"
done
```
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add skills/performance/SKILL.md
git commit -m "fix(performance): SKILL.md dispatches to per-stack reference files, adds host-doc partial-coverage merge rule, delegates BASE_URL fully to api-load.md, removes unused WebFetch permission"
```

---

## Task 7: Fix `api-load.md` — BASE_URL confirmation, file-path consistency, k6 scenario auto-generation

**Files:**
- Modify: `skills/performance/references/api-load.md`

**Interfaces:**
- Produces: a confirmed `BASE_URL` + a saved OpenAPI spec at a fixed path, consumed by the k6-scenario generator script in the same file.

- [ ] **Step 1: Reproduce the confirmed missing-confirmation + missing-file bugs**

```bash
grep -n "confirm\|AskUserQuestion" skills/performance/references/api-load.md
```
Expected: no match (confirms today's gap — no confirmation step exists).
```bash
grep -n "^BASE_URL=" skills/performance/references/api-load.md
```
Expected: shows the silent-default line `BASE_URL="${1:-http://localhost:8000}"` with no confirmation around it.

- [ ] **Step 2: Rewrite §1.1 with multi-source detection + required confirmation (mirrors playwright-scaffold)**

Replace §1.1 (original lines 9-39) with:

```markdown
## 1. Automatic OpenAPI Spec Discovery + BASE_URL Confirmation

### 1.1 BASE_URL Detection (multi-source, with required user confirmation)

Do not hardcode or silently default BASE_URL. Gather candidates, then **confirm with the user** before use
(same principle as `playwright-scaffold`'s baseURL detection):

```bash
# 1) flow-config.yaml (host-shared config, if this project uses the harness-tier flow)
grep -A2 "contract_test:" .claude/harness-tier/config/flow-config.yaml 2>/dev/null | grep "base_url"

# 2) docker-compose port mapping (backend service host port)
grep -nE '^\s*-\s*"?[0-9]+:[0-9]+' docker-compose.y*ml compose.y*ml 2>/dev/null

# 3) PORT / BASE_URL in .env
grep -nhE '^(PORT|BASE_URL)=' .env .env.* 2>/dev/null

# 4) framework-default ports (if nothing above matched)
#    FastAPI/Django=8000, Spring Boot=8080, ASP.NET=5000/7000, Rails/Express=3000
```

**User confirmation (required)**: present the collected candidates via `AskUserQuestion` and finalize
`BASE_URL` (offer them as choices if there are several; ask for direct input if none was found). Do not
assert a guess as fact — this mirrors `playwright-scaffold`'s Step 1 exactly.

### 1.2 Candidate-Path Order

If the server is running, GET the paths below in order using the confirmed `BASE_URL`. Use the first
successful response.

| Priority | Path | Framework | Source |
|---|---|---|---|
| 1 | `/openapi.json` | FastAPI | https://fastapi.tiangolo.com/tutorial/metadata/ |
| 2 | `/v3/api-docs` | springdoc-openapi | https://github.com/springdoc/springdoc-openapi |
| 3 | `/swagger/v1/swagger.json` | ASP.NET Swashbuckle (default documentName `v1`) | https://learn.microsoft.com/en-us/aspnet/core/tutorials/getting-started-with-swashbuckle |
| 4 | `/swagger.json` | Common convention | — |
| 5 | `/api-docs` | Common convention | — |

**Handling the variable ASP.NET documentName**: if `/swagger/v1/swagger.json` fails, fetch the
`/swagger` HTML and parse the `url: "..."` pattern inside a `<script>` tag to extract the actual spec URL.

```bash
# Save the spec to a fixed, shared path — every later step in this file (openapi-to-k6, the scenario
# generator) reads from this exact path, so there is only one file location to keep in sync.
mkdir -p /tmp/harness-perf
SPEC_PATH="/tmp/harness-perf/openapi_spec.json"
SPEC_URL=""
for path in /openapi.json /v3/api-docs /swagger/v1/swagger.json /swagger.json /api-docs; do
  if curl -sf "${BASE_URL}${path}" -o "$SPEC_PATH"; then
    SPEC_URL="${BASE_URL}${path}"
    echo "spec found: ${SPEC_URL} -> ${SPEC_PATH}"
    break
  fi
done
if [ -z "$SPEC_URL" ]; then
  echo "OpenAPI spec not found — check server is running and spec endpoint is enabled"
  exit 1
fi
```
```

- [ ] **Step 3: Verify the confirmation step and the fixed save path are both present**

```bash
grep -c "AskUserQuestion" skills/performance/references/api-load.md
```
Expected: `>= 1`.
```bash
grep -n 'SPEC_PATH="/tmp/harness-perf/openapi_spec.json"' skills/performance/references/api-load.md
```
Expected: one match.

- [ ] **Step 4: Fix the pre-existing k6 executor math bug (`per-vu-iterations` runs `vus × iterations`, not `iterations`)**

This bug predates this plan and was missed by the original review — it is not one of the 11 confirmed findings,
but it directly breaks the "100 times per endpoint" promise this file makes, so fix it here.

Reproduce it against k6's own documented semantics (no local k6 install needed — this is a config-math check):
```bash
grep -n "executor: 'per-vu-iterations'" skills/performance/references/api-load.md
```
Expected (before fix): two matches (`get_users`, `create_order`), each with `vus: 10, iterations: 100` — per
k6's docs, `per-vu-iterations` makes **each** of the 10 VUs run 100 iterations independently, for a **total of
1000** iterations per endpoint (`vus * iterations`), not the 100 the report template promises.

Fix: replace `executor: 'per-vu-iterations'` with `executor: 'shared-iterations'` in the existing two-endpoint
example (§2.1's worked example) — `shared-iterations`' `iterations` field is the **total** count shared across
all VUs (per k6 docs: "Total number of script iterations to execute across all VUs"), which is what "100 times
per endpoint" actually requires:

```javascript
// /tmp/harness-perf/k6-load.js — per-endpoint scenarios (100 TOTAL iterations each, shared across 10 VUs)
import { getUsers, createOrder } from './k6-client.js'; // functions generated by openapi-to-k6
export const options = {
  scenarios: {
    get_users:    { executor: 'shared-iterations', vus: 10, iterations: 100, exec: 'getUsers' },
    create_order: { executor: 'shared-iterations', vus: 10, iterations: 100, exec: 'createOrder' },
  },
};
export function getUsers()    { /* call GET /users via the generated client */ }
export function createOrder() { /* call POST /orders via the generated client */ }
```

Verify:
```bash
grep -c "executor: 'per-vu-iterations'" skills/performance/references/api-load.md
```
Expected (after fix): `0`.
```bash
grep -c "executor: 'shared-iterations'" skills/performance/references/api-load.md
```
Expected (after fix): `>= 2`.

Also add a one-line callout directly above the example clarifying the distinction, so a future editor doesn't
revert to `per-vu-iterations` by habit:
```markdown
> **Executor choice matters**: `shared-iterations` treats `iterations` as a TOTAL shared across all `vus`
> (exactly "100 per endpoint"). `per-vu-iterations` instead runs `iterations` **per VU**, i.e. `vus * iterations`
> total — using it here would silently run 1000 iterations per endpoint instead of the promised 100.
```

- [ ] **Step 5: Add the k6 scenario auto-generation script (§2.1), replacing the "generate programmatically" placeholder sentence**

Locate the existing §2.1 "Running (100 times per endpoint)" subsection and, immediately after the two-endpoint
example, replace the line `"When there are many endpoints, generate the scenarios above programmatically..."`
with a concrete, runnable generator:

```markdown
**Generating scenarios for an arbitrary number of endpoints:**

The two-scenario example above is illustrative. For any real spec, generate `k6-load.js` programmatically by
pairing the spec's operation list with `k6-client.js`'s actual exported function names (positionally, in
declaration order) — this avoids hardcoding assumptions about openapi-to-k6's naming convention:

```javascript
// /tmp/harness-perf/gen-k6-scenarios.mjs
// Usage: node gen-k6-scenarios.mjs <spec.json> <k6-client.js> <output k6-load.js>
import fs from 'fs';

const [specPath, clientPath, outPath] = process.argv.slice(2);
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));

const operations = [];
for (const [urlPath, methods] of Object.entries(spec.paths || {})) {
  for (const [method, op] of Object.entries(methods)) {
    if (!['get', 'post', 'put', 'patch', 'delete'].includes(method)) continue;
    operations.push({ method: method.toUpperCase(), path: urlPath, operationId: op.operationId });
  }
}

const clientSrc = fs.readFileSync(clientPath, 'utf8');
const exportedFns = [...clientSrc.matchAll(/export\s+(?:async\s+)?function\s+(\w+)/g)].map(m => m[1]);

if (exportedFns.length !== operations.length) {
  console.error(
    `Mismatch: spec has ${operations.length} operations but ${clientPath} exports ${exportedFns.length} ` +
    `functions — verify openapi-to-k6's naming convention manually before generating scenarios.`
  );
  process.exit(1);
}

const scenarios = {};
operations.forEach((op, i) => {
  const fn = exportedFns[i];
  const scenarioKey = fn.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
  // shared-iterations: `iterations` is the TOTAL shared across all `vus` (exactly "100 per endpoint").
  // per-vu-iterations would instead run 100 PER VU = vus*iterations total — do not use it here.
  scenarios[scenarioKey] = { executor: 'shared-iterations', vus: 10, iterations: 100, exec: fn };
});

const out = `import * as client from './k6-client.js';
export const options = {
  scenarios: ${JSON.stringify(scenarios, null, 2)},
};
${exportedFns.map(fn => `export function ${fn}() { client.${fn}(); }`).join('\n')}
`;
fs.writeFileSync(outPath, out);
console.log(`Generated ${operations.length} scenarios -> ${outPath}`);
```

```bash
node /tmp/harness-perf/gen-k6-scenarios.mjs /tmp/harness-perf/openapi_spec.json /tmp/harness-perf/k6-client.js /tmp/harness-perf/k6-load.js
k6 run --out json=/tmp/harness-perf/k6-result.json /tmp/harness-perf/k6-load.js
```
```

- [ ] **Step 6: Test the generator script against a tiny fixture (proves the operation↔export pairing logic AND the executor fix both work)**

```bash
mkdir -p /tmp/harness-k6-fixture
cat > /tmp/harness-k6-fixture/spec.json <<'EOF'
{"paths": {"/users": {"get": {"operationId": "getUsers"}}, "/orders": {"post": {"operationId": "createOrder"}}}}
EOF
cat > /tmp/harness-k6-fixture/k6-client.js <<'EOF'
export function getUsers() {}
export function createOrder() {}
EOF
node /tmp/harness-perf/gen-k6-scenarios.mjs /tmp/harness-k6-fixture/spec.json /tmp/harness-k6-fixture/k6-client.js /tmp/harness-k6-fixture/k6-load.js
cat /tmp/harness-k6-fixture/k6-load.js
grep -c "shared-iterations" /tmp/harness-k6-fixture/k6-load.js
```
Expected: prints "Generated 2 scenarios -> ...k6-load.js", the generated file contains a `scenarios` object
with `get_users` and `create_order` keys, `iterations: 100` each, both `exec` targets exported as top-level
functions, and the `grep -c` line prints `2` (both scenarios use `shared-iterations`, not `per-vu-iterations`
— confirming each endpoint gets exactly 100 total iterations, not 1000). Clean up:
```bash
rm -rf /tmp/harness-k6-fixture /tmp/harness-perf
```

- [ ] **Step 7: Update §3 report format's measurement metadata to note the confirmation step happened**

Add one line to the "Measurement metadata" bullet list in §3.3 (Required to record): `Confirmed BASE_URL:
<value> (source: flow-config / docker-compose / .env / framework-default / user-provided)`.

- [ ] **Step 8: Commit**

```bash
git add skills/performance/references/api-load.md
git commit -m "fix(performance): add BASE_URL confirmation step, unify spec file path, fix k6 executor math bug (per-vu-iterations -> shared-iterations), add k6 scenario auto-generation script for N-endpoint specs"
```

---

## Task 8: Create `integration/references/electron.md` (Electron hybrid procedure — single SSOT)

**Files:**
- Create: `skills/integration/references/electron.md`

**Interfaces:**
- Produces: `electron.md` — Task 9 (SKILL.md `## 4. If Electron`) and Task 10/11 (trimmed cross-references) point here as the sole source of the Electron exception text.

- [ ] **Step 1: Write `electron.md`**

```markdown
# Electron Integration Testing — Hybrid Procedure (SSOT)

> Electron apps are neither pure Web nor pure Non-web: the renderer process is Chromium-based and can be
> driven by Playwright; the main process (Node.js, IPC, filesystem, native APIs) cannot. **This file is the
> single source of truth for the Electron exception** — other files link here instead of restating it.

---

## 1. Renderer-Process Automation (Playwright)

Playwright supports Electron directly via `_electron.launch()` — **not** the plain `chromium` browser channel,
which cannot attach to an existing Electron app's renderer process:

```javascript
const { _electron: electron } = require('playwright');
const app = await electron.launch({ args: ['main.js'] });
const window = await app.firstWindow();
await window.waitForLoadState('domcontentloaded');
// assertions against `window` use the same Locator API as a normal Page
await app.close();
```

Source: https://playwright.dev/docs/api/class-electron (Apache-2.0)

Reuse the same `playwright.config.*`/`testDir`/`--reporter=json,junit` conventions as
[`web-playwright.md`](web-playwright.md) §2-§3 for the renderer suite — only the launch mechanism differs
(`_electron.launch()` instead of `browser.newPage()`).

## 2. Main-Process Scenarios — human-in-the-loop

IPC handlers, filesystem access, and native OS integration (menus, tray, notifications) are not reachable
through Playwright. Collect these via `AskUserQuestion`, following the same procedure as
[`non-web.md`](non-web.md) §2 (scenarios + pass criteria + manual checklist).

## 3. Report Format

```
## Electron Integration Test Results — <date>

### Renderer (Playwright)
| Suite | Passed | Failed | Skipped | Verdict |
|---|---|---|---|---|
| tests/renderer/app.spec.ts | 4 | 0 | 0 | PASS |

### Main Process (manual checklist)
| Scenario | Verdict |
|---|---|
| IPC: save-file dialog returns a valid path | PASS |

**Overall verdict**: PASS
```

## 4. SSOT URL Summary

| Item | URL | License |
|---|---|---|
| Playwright Electron API | https://playwright.dev/docs/api/class-electron | Apache-2.0 |
| Playwright ElectronApplication | https://playwright.dev/docs/api/class-electronapplication | Apache-2.0 |
```

- [ ] **Step 2: Verify the file was created and links resolve**

```bash
test -f skills/integration/references/electron.md && grep -c "non-web.md\|web-playwright.md" skills/integration/references/electron.md
```
Expected: `2` (one link to each).

- [ ] **Step 3: Commit**

```bash
git add skills/integration/references/electron.md
git commit -m "feat(integration): add electron.md as the single source of truth for the Electron hybrid procedure"
```

---

## Task 9: Rewrite `integration/SKILL.md` — Electron branch, go.mod signal, find-glob fix, r.stats defensive parsing

**Files:**
- Modify: `skills/integration/SKILL.md`

**Interfaces:**
- Consumes: `references/electron.md` (Task 8).
- Produces: renumbered sections (`## 5. If Non-Web`, was `## 4.`) — Task 10/11 do not depend on the exact numbers, only on the file names, so no further renumbering ripple.

- [ ] **Step 1: Reproduce the confirmed detection-table / classification-precedence gap**

```bash
grep -n '"react-native"\\|"electron"' skills/integration/SKILL.md
```
Expected: shows the current non-web grep that folds Electron into Non-web (confirms the bug before the fix).

- [ ] **Step 2: Rewrite §2's detection table and commands — Electron checked first, go.mod added**

Replace the current §2 body (lines 33-67) with:

```markdown
## 2. Web-Frontend / Electron / Non-web Detection (heuristic)

> For the full list of detection signals and its limitations, see → [`references/web-playwright.md`](references/web-playwright.md).

Check **Electron first** — it is a distinct verdict, not folded into Non-web:

```bash
grep '"electron"' package.json 2>/dev/null
```

If not Electron, check `package.json`'s `dependencies`/`devDependencies` against a web-framework allowlist:

```bash
# Check for web-framework dependencies
grep -E '"(react|vue|next|nuxt|svelte|@angular/core|solid-js|astro)"' package.json 2>/dev/null
```

Also check the supporting signals:

```bash
# Supporting signals: vite.config, index.html, public/
ls vite.config.* index.html public/ 2>/dev/null
```

Check the **other non-web signals** (if present, classify as non-web):

```bash
# CLI: bin field, RN: react-native/metro.config.js, Flutter: pubspec.yaml, Go: go.mod/main.go
grep '"bin"' package.json 2>/dev/null
grep '"react-native"' package.json 2>/dev/null
ls metro.config.js pubspec.yaml go.mod main.go 2>/dev/null
```

| Verdict | Condition |
|---|---|
| **Electron** | An `"electron"` dependency exists (checked **before** any other signal) |
| **Web** | No Electron signal + an allowlist dependency exists + no other non-web signal |
| **Non-web** | No Electron signal + a non-web signal exists (CLI/RN/Flutter/Go/etc.), or no allowlist match |

> For the full **Electron** procedure (renderer automation + main-process human-in-the-loop), see
> [`references/electron.md`](references/electron.md) — the single source of truth for this exception.
```

- [ ] **Step 3: Reproduce and fix the confirmed find-glob drift (§3.2 case discovery)**

Reproduce the bug — build a fixture with a `.spec.mjs` file and show the old command misses it:
```bash
mkdir -p /tmp/harness-int-fixture/tests
touch /tmp/harness-int-fixture/tests/checkout.spec.mjs
find /tmp/harness-int-fixture/tests -name "*.spec.ts" -o -name "*.spec.js" -o -name "*.test.ts" -o -name "*.test.js"
```
Expected: no output (confirms the bug — the file exists but isn't found).

Verify the fixed regex-based command finds it:
```bash
find /tmp/harness-int-fixture/tests -regextype posix-extended -regex '.*\.(spec|test)\.(c|m)?[jt]sx?'
```
Expected: `/tmp/harness-int-fixture/tests/checkout.spec.mjs` printed. Clean up:
```bash
rm -rf /tmp/harness-int-fixture
```

Replace §3.2's `find` command (current lines 89-92) with:

```markdown
### 3.2 Discover Existing Cases

```bash
# Matches the testMatch default exactly: **/*.@(spec|test).?(c|m)[jt]s?(x)
find ./tests -regextype posix-extended -regex '.*\.(spec|test)\.(c|m)?[jt]sx?' 2>/dev/null | wc -l
```
```

- [ ] **Step 4: Reproduce and fix the confirmed `r.stats` crash bug (§3.4)**

Reproduce — a `results.json` missing `stats` crashes the old parser:
```bash
echo '{}' > /tmp/bad-results.json
node -e "
  const r = JSON.parse(require('fs').readFileSync('/tmp/bad-results.json','utf8'));
  const s = r.stats;
  console.log('PASS:', s.expected, '/ FAIL:', s.unexpected, '/ SKIP:', s.skipped);
  process.exit(s.unexpected > 0 ? 1 : 0);
" ; echo "exit code: $?"
```
Expected: `TypeError: Cannot read properties of undefined` and a non-clean exit — confirms the bug.

Verify the defensive version handles it gracefully:
```bash
node -e "
  const fs = require('fs');
  let r;
  try { r = JSON.parse(fs.readFileSync('/tmp/bad-results.json', 'utf8')); }
  catch (e) { console.log('FAIL: results.json missing or invalid (' + e.message + ')'); process.exit(1); }
  const s = r && r.stats;
  if (!s || typeof s.unexpected !== 'number') {
    console.log('FAIL: results.json has no stats — the Playwright run likely crashed before completing');
    process.exit(1);
  }
  console.log('PASS:', s.expected, '/ FAIL:', s.unexpected, '/ SKIP:', s.skipped);
  process.exit(s.unexpected > 0 ? 1 : 0);
" ; echo "exit code: $?"
rm /tmp/bad-results.json
```
Expected: prints `FAIL: results.json has no stats...` and exits `1` cleanly (no stack trace).

Replace §3.4's parsing script (current lines 118-130) with:

```markdown
### 3.4 Parse Results and Report PASS/FAIL

Parse the `results.json` specified in §3.3, defensively (a crashed or incomplete Playwright run must still
produce a clear FAIL report, not an uncaught exception):

```bash
node -e "
  const fs = require('fs');
  let r;
  try { r = JSON.parse(fs.readFileSync('results.json', 'utf8')); }
  catch (e) { console.log('FAIL: results.json missing or invalid (' + e.message + ')'); process.exit(1); }
  const s = r && r.stats;
  if (!s || typeof s.unexpected !== 'number') {
    console.log('FAIL: results.json has no stats — the Playwright run likely crashed before completing');
    process.exit(1);
  }
  console.log('PASS:', s.expected, '/ FAIL:', s.unexpected, '/ SKIP:', s.skipped);
  process.exit(s.unexpected > 0 ? 1 : 0);
"
```
```

- [ ] **Step 5: Insert the new `## 4. If Electron` section, renumber the old `## 4. If Non-Web` to `## 5.`**

Insert immediately after the current `## 3. If Web` section (before the old `## 4. If Non-Web`):

```markdown
## 4. If Electron — hybrid (renderer automation + main-process human-in-the-loop)

> For the full procedure and SSOT, see → [`references/electron.md`](references/electron.md).

Electron is a **distinct third verdict**, not folded into Non-web — it gets **partial automation**.

1. Run the renderer-process suite the same way as §3 "If Web" (same `playwright.config.*` parsing, same
   `--reporter=json,junit` run, same defensive result parsing from §3.4) — see `references/electron.md` §1
   for the Electron-specific Playwright launch (`_electron.launch()`, not a plain `chromium` channel).
2. For main-process scenarios (IPC handlers, filesystem access, native menus), use the same human-in-the-loop
   procedure as `## 5. If Non-web` below — collect scenarios via `AskUserQuestion` and produce a manual
   checklist.
3. Report both results together: a Playwright PASS/FAIL table for the renderer + a manual checklist for the
   main process (see `references/electron.md` §3 for the combined report template).
```

Then change the old `## 4. If Non-Web` heading to `## 5. If Non-Web`.

- [ ] **Step 6: Fix the Non-web `AskUserQuestion` prompt to substitute the actually-detected type instead of a hardcoded generic list**

Reproduce the confirmed gap — the current prompt hardcodes a generic list instead of using the detected signal:
```bash
grep -n "detected as non-web (CLI/RN/Flutter, etc.)" skills/integration/SKILL.md
```
Expected (before fix): one match. Compare against the reference file's own template, which is already
correctly parameterized:
```bash
grep -n "detected as non-web (<type>)" skills/integration/references/non-web.md
```
Expected: one match — confirms `SKILL.md` should follow this same `<type>` pattern instead of hardcoding.

Fix: in the (renumbered) `## 5. If Non-Web` section, replace the hardcoded prompt line with an instruction to
substitute the specific signal detected in §2 (e.g. `"bin"` field → CLI, `react-native` → React Native,
`pubspec.yaml` → Flutter, `go.mod`/`main.go` → Go, no allowlist match → generic):

```markdown
Do not enforce automated integration testing. Determine the specific non-web type from the §2 signal that
matched (CLI / React Native / Flutter / Go / generic — do not fall back to a generic list if a specific
signal matched), then collect scenarios and pass criteria via `AskUserQuestion` using that type:

```
This project was detected as non-web (<type>).
No integration-test automation tool is enforced.

Please provide the following:
1. The core scenarios to verify (e.g., "look up data after user login")
2. The pass criteria for each scenario (e.g., "response code 200, data included")
3. Any test tool you are currently using, if any.
```
```

Verify the hardcoded generic list is gone and the parameterized form matches `non-web.md`'s template:
```bash
grep -n "detected as non-web (CLI/RN/Flutter, etc.)" skills/integration/SKILL.md
```
Expected (after fix): no output.
```bash
grep -n "detected as non-web (<type>)" skills/integration/SKILL.md
```
Expected (after fix): one match.

- [ ] **Step 7: Verify section numbering and all cross-references are consistent**

```bash
grep -n "^## " skills/integration/SKILL.md
```
Expected order: `## 1. Consume Host Documentation First`, `## 2. Web-Frontend / Electron / Non-web Detection (heuristic)`, `## 3. If Web — Run Existing Playwright Cases`, `## 4. If Electron — ...`, `## 5. If Non-Web — human-in-the-loop`, `## References`.

```bash
grep -n "§4\|§5" skills/integration/SKILL.md
```
Manually confirm every `§4`/`§5` mention refers to the correct (post-renumbering) section.

- [ ] **Step 8: Commit**

```bash
git add skills/integration/SKILL.md
git commit -m "fix(integration): add Electron as a first-class branch, add go.mod signal, fix testMatch find-glob drift, defend r.stats parsing against crashed runs, substitute detected type into the non-web prompt"
```

---

## Task 10: Fix `integration/references/web-playwright.md` — find-glob alignment, Electron row removal

**Files:**
- Modify: `skills/integration/references/web-playwright.md`

**Interfaces:**
- Consumes: `references/electron.md` (Task 8) for the replacement pointer text.

- [ ] **Step 1: Fix §3.1's find command to match testMatch exactly (same regex as Task 9 Step 3)**

Replace the current §3.1 command (original lines 82-89) with:

```markdown
### 3.1 Discovering case files

```bash
# Matches the testMatch default exactly: **/*.@(spec|test).?(c|m)[jt]s?(x)
find ./tests -regextype posix-extended -regex '.*\.(spec|test)\.(c|m)?[jt]sx?' 2>/dev/null
```
```

- [ ] **Step 2: Remove the Electron row from the "Non-web signals" table (§1.3) and its inline exception prose; replace with a pointer**

Replace the current §1.3 (original lines 38-52), which lists Electron as a non-web-signal table row and then
restates the exception in prose, with:

```markdown
### 1.3 Non-web signals (if present, the non-web verdict takes precedence)

| Signal | Verdict |
|---|---|
| `"bin"` field in `package.json` | CLI tool |
| `"react-native"` dependency | React Native (mobile) |
| `metro.config.js` | React Native bundler |
| `pubspec.yaml` | Flutter |
| `main.go` / `go.mod` (+ no web signals) | Go CLI/service |

> **Electron is not listed here** — it is checked *before* this table (see `integration/SKILL.md` §2) and is
> its own verdict, not a non-web signal. For the full procedure, see [`electron.md`](electron.md).
```

- [ ] **Step 3: Verify the old Electron prose is gone and the new pointer is present**

```bash
grep -n "partial automation of the renderer" skills/integration/references/web-playwright.md
```
Expected: no output (old restated prose removed).
```bash
grep -c "electron.md" skills/integration/references/web-playwright.md
```
Expected: `>= 1`.

- [ ] **Step 4: Commit**

```bash
git add skills/integration/references/web-playwright.md
git commit -m "fix(integration): align web-playwright.md find-glob with testMatch, move Electron exception to electron.md"
```

---

## Task 11: Fix `integration/references/non-web.md` — remove duplicated Electron prose

**Files:**
- Modify: `skills/integration/references/non-web.md`

**Interfaces:**
- Consumes: `references/electron.md` (Task 8) for the replacement pointer text.

- [ ] **Step 1: Reproduce the confirmed duplication**

```bash
grep -n "Chromium renderer process can be partially automated" skills/integration/references/non-web.md
```
Expected: match found (confirms the duplicate prose exists before the fix).

- [ ] **Step 2: Remove the Electron row from §1's "Per-Type Non-Web Signals" table and its restated exception paragraph**

Replace the current §1 (original lines 9-27), which includes an `**Electron**` row in the signals table and a
full restated "Electron exception" paragraph, with:

```markdown
## 1. Per-Type Non-Web Signals

| Type | Detection signal | Notes |
|---|---|---|
| **CLI tool** | A `"bin"` field in `package.json` | Node.js CLI |
| | `main.go` + a `cobra`/`urfave/cli` dependency | Go CLI |
| | `[project.scripts]` in `pyproject.toml` or `entry_points` in `setup.py` | Python CLI |
| **React Native** | `"react-native"` dependency | iOS/Android app |
| | `metro.config.js` present | RN bundler signal |
| **Flutter** | `pubspec.yaml` present | iOS/Android/Desktop |
| **Go service/CLI** | `go.mod` + no web-framework dependency | Non-web if there is no frontend, even with an HTTP server |
| **Python service** | `pyproject.toml`/`requirements.txt` + no web-framework dependency | FastAPI/Django are backends — distinguish from a web frontend |

> **Electron is not a non-web type** — it is its own verdict, checked before this table (see
> `integration/SKILL.md` §2). See [`electron.md`](electron.md) for the full hybrid procedure.
```

- [ ] **Step 3: Update §4's two Electron rows to point at `electron.md` instead of restating logic**

In the "Recommended Approach by Non-Web Type" table (original §4), update the "Reference tool" column for
both Electron rows (`Electron (renderer)` and `Electron (main process, IPC)`) to read `[electron.md](electron.md)`
instead of `web-playwright.md` / `—`.

- [ ] **Step 4: Verify the duplicated prose is gone**

```bash
grep -n "Chromium renderer process can be partially automated" skills/integration/references/non-web.md
```
Expected: no output.
```bash
grep -c "electron.md" skills/integration/references/non-web.md
```
Expected: `>= 2` (§1 pointer + §4 table references).

- [ ] **Step 5: Commit**

```bash
git add skills/integration/references/non-web.md
git commit -m "fix(integration): remove duplicated Electron exception prose from non-web.md, point to electron.md"
```

---

## Task 12: Align `playwright-scaffold/SKILL.md` idempotency glob + full cross-file consistency sweep

**Files:**
- Modify: `skills/playwright-scaffold/SKILL.md`

**Interfaces:**
- Final task — verifies Tasks 1-11 are internally consistent as a whole.

- [ ] **Step 1: Align the idempotency check (Step 3) to the same testMatch-equivalent regex**

Replace the current Step 3 command (original line 59):

```bash
find "${TESTDIR:-tests}" \( -name '*.spec.*' -o -name '*.test.*' \) 2>/dev/null | head -1
```

with:

```bash
# Matches the testMatch default exactly — same pattern used by integration/SKILL.md and web-playwright.md,
# so all three files agree on what counts as "an existing case" (previously this used a broader `*.spec.*`
# wildcard that could also match non-Playwright files like `foo.spec.md`).
find "${TESTDIR:-tests}" -regextype posix-extended -regex '.*\.(spec|test)\.(c|m)?[jt]sx?' 2>/dev/null | head -1
```

- [ ] **Step 2: Verify the three testMatch-glob sites now use the identical regex**

```bash
grep -h "regextype posix-extended" skills/integration/SKILL.md skills/integration/references/web-playwright.md skills/playwright-scaffold/SKILL.md
```
Expected: three lines, all containing the identical `-regex '.*\.(spec|test)\.(c|m)?[jt]sx?'` pattern.

- [ ] **Step 3: Full dangling-reference sweep across both skills**

```bash
grep -rn "static-checks.md" skills/performance/ | grep -v "static-checks-"
```
Expected: no output.

```bash
for f in python java ruby dotnet node react db complexity; do
  grep -rl "static-checks-$f.md" skills/performance/ >/dev/null || echo "UNREFERENCED: static-checks-$f.md"
done
```
Expected: no output (every new file is linked from somewhere).

```bash
grep -rn "electron.md" skills/integration/ | wc -l
```
Expected: `>= 4` (SKILL.md §2 and §4, web-playwright.md §1.3, non-web.md §1 and §4).

```bash
grep -c "WebFetch" skills/performance/SKILL.md
grep -c "executor: 'per-vu-iterations'" skills/performance/references/api-load.md
grep -n "detected as non-web (CLI/RN/Flutter, etc.)" skills/integration/SKILL.md
```
Expected: all three commands produce **no match / zero** — confirms the 3 additional bugs found during plan
review (unused `WebFetch` permission, k6 `per-vu-iterations` executor math bug, hardcoded non-web type list)
are fixed, not just the original 11.

- [ ] **Step 4: Confirm the design spec's 14 findings all map to a completed task**

Manually cross-check each of the 11 rows in `docs/superpowers/specs/2026-07-06-performance-integration-skill-fixes-design.md`
§2, plus the 3 addendum findings (§2a), against Tasks 1-11 above — every row must have a corresponding fix.
Note any gap here before proceeding.

- [ ] **Step 5: Commit**

```bash
git add skills/playwright-scaffold/SKILL.md
git commit -m "fix(playwright-scaffold): align idempotency glob with the testMatch-equivalent regex used across integration skill files"
```
