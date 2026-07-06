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
