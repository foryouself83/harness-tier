# Project harness

**English** · [한국어](project-harness.ko.md) · [Usage guide](../../USAGE.md)

## `/harness-init` — generate the project harness

```text
/harness-init     # no arguments — interactive wizard
```

Generates `CLAUDE.md`, `.claude/rules/` and technical docs tailored to your project — a separate,
independent command from `/flow-init`. Skip it only if you already have a well-formed `CLAUDE.md`;
skipping it also means `/flow-init` has no `docs/code-style/` to draft `modules[].checks` from, and
`docs/operations/commit-versioning-guide.md` and `docs/verification/*.md` are never generated for
`/commit`, `/integration` and `/performance` to read.

1. **Interview** — before research, it fixes the scope so nothing downstream guesses:
   - clarifies every ambiguous or blank requirement via `AskUserQuestion` when generating an SRS,
     for greenfield and brownfield alike (a brownfield SRS still gets only a skeleton, with
     unresolved slots marked "needs confirmation");
   - always confirms the primary development language, even when detected, and maps it per layer
     (frontend/backend/other) when they differ;
   - confirms the detected framework and version;
   - lets you choose which artifacts to generate — CLAUDE.md, rules, skills, agents, technical
     docs — there is no default set;
   - asks, item by item, about real configuration: a security scanner, CI, real folder scaffolding,
     version pins.
2. **Research** — parallel subagents (`harness-researcher` for web conventions and free
   off-the-shelf solutions; `harness-code-analyzer` on a brownfield repo for its real conventions)
   converge on a stack that boots together, not each dependency's own latest.
3. **Generation** — produces the chosen artifacts into classified folders, plus a `rationale.md`
   recording why. Evidence — `plan.json`, `manifest.json`, `critic-report.json`, `rationale.md` —
   is written to `.claude/harness-tier/.harness/` (gitignored) for audit and re-run.
4. **Critique** — `harness-critic` checks quality, cross-file coherence and version compatibility,
   and refines the output.
5. **Preview then confirm** — shows what it will create, and writes only after you confirm.
6. **Cleanup** — removes the research copies merged into docs, keeping the evidence metadata. A
   copy still referenced by a doc is kept and reported, rather than leaving a broken link.

- **No overwrite** — an existing file is updated only in managed blocks; conflicts are reported,
  and you choose skip or overwrite per item on a brownfield conflict.
- **`.claude/rules/`, not only `CLAUDE.md`** — framework and structural conventions become
  auto-loaded `.claude/rules/<name>.md` files, each with an optional `paths` glob so it loads only
  for matching files. `/doc-sync` keeps them in step with the code.
- **It does not generate slash commands.**
- **Do not commit** — commit through [`/flow`](daily-work.md#flow--the-day-to-day-router). If this
  run created `docs/srs/`, re-run `/flow-init` afterward so it can offer `srs-verify.yml`.

### Auto-detected languages and frameworks

Step 1 fingerprints your stack from its manifest files.

| Language | Manifest(s) | Auto-detected frameworks / libraries |
|----------|-------------|--------------------------------------|
| Python | `pyproject.toml` · `requirements.txt` | FastAPI · Django · Flask |
| JavaScript / TypeScript | `package.json` | Next.js · React · Vue · Nuxt · Svelte · Angular · Express · NestJS |
| Go | `go.mod` | (module-level) |
| Java | `pom.xml` · `build.gradle[.kts]` | Spring Boot · Spring · Quarkus · Micronaut · Ktor |
| Kotlin | `build.gradle.kts` · `pom.xml` | shares the JVM table above |
| C# | `*.csproj` | ASP.NET Core · Blazor WASM · Razor · WPF · WinForms · MAUI · EF Core |
| C++ | `CMakeLists.txt` · `vcpkg.json` · `conanfile.*` | CMake · Boost · Qt · OpenCV · GoogleTest · Catch2 · fmt · spdlog |
| Rust | `Cargo.toml` | actix-web · axum · Rocket · warp · tokio |
| PHP | `composer.json` | Laravel · Symfony · Slim · CodeIgniter |
| Ruby | `Gemfile` | Rails · Sinatra · Hanami |
| Swift | `Package.swift` · `*.xcodeproj`/`*.xcworkspace` | Vapor · SwiftNIO · Alamofire · RxSwift |
| Scala | `build.sbt` | Play · Akka · Akka HTTP · http4s · Cats Effect |

A stack outside this table still gets a harness — greenfield vs. brownfield comes from source
file extensions, and `harness-researcher` researches conventions for whatever framework you use;
only the deterministic fingerprint above is limited to these entries.

## `/wiki-init` — build the docs into a knowledge graph

```text
/wiki-init   # no arguments — interactive; disable-model-invocation, call it explicitly
```

**Precondition**: `.claude/harness-tier/config/flow-config.yaml` must exist. Run `/flow-init`
first if it does not.

Migrates existing docs into one-concept-per-file nodes with YAML front matter, no embeddings, and
generates `docs/graph/graph.yaml`. Relationships are the front matter you write by hand,
mechanically read into the graph; originals are not deleted, only linked. It is idempotent — a
document that already carries a `wiki_id` is never re-offered.

It ends by setting `flow-config.wiki.enable: true` and running
`wiki_graph.py --build` then `--verify`. If verify does not pass in the same session, it sets
`enable` back to `false` before finishing, rather than leave every commit in the repo blocked on
a graph nobody fixed. Once verify passes, it offers `wiki-verify.yml`
([CI workflows](ci-workflows.md)) — declining it leaves graph drift from outside a Claude session
uncaught until someone's next session commit.

Once built, [`/doc-sync`](daily-work.md#doc-sync--keep-the-docs-in-step) keeps the graph and each
node's `sources` stamp in sync, and the [`wiki` gate](tiers-and-gates.md#wiki) verifies that sync,
read-only, at every commit. The graph is also a development read path:
[`/flow`](daily-work.md#flow--the-day-to-day-router)'s Dev track maps the files about to change to
their documenting nodes before planning.

## `harness-insight` — activity and memory review

```text
/harness-insight [period]   # e.g. 7 days · 2 weeks · 30 days · today (default 7 days)
```

Aggregates the Claude Code transcript — sent prompts and tool use — over the period, and prints a
report in the conversation: work distribution, repeated instructions worth turning into a harness
rule, activity hotspots, and next actions. It then reviews the accumulated project memory and
proposes deletions or promotions to `.claude/rules` or `docs/`, applied only after you approve.
No report file is written — its intermediate files are deleted after the report prints. A cwd
Claude Code has never worked in stops it with a message rather than a guess.
