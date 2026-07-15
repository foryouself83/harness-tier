# {{STACK_LABEL}} Code Style

> {{LANGUAGE}} + {{FRAMEWORK_OR_PLATFORM}}. Describe the discipline in prose, **without code snippets**. Sources: {{SOURCES}}

## Naming · Formatting · Imports
{{STYLE_RULES}}

## Best Practices (by quality lens)
<!-- Organize into per-lens sub-sections; emit ONLY the lenses that apply to this stack (harness-rules 9-7 · 9-8, 9-2 evidence-based).
     1-2 lines + source each. Coding guidance only — link the SSOT that owns the rest, never duplicate it. Drop the ### heading of any lens
     that does not apply (no empty sections). -->
{{BEST_PRACTICES_BY_LENS}}
<!-- shape (keep only applicable lenses):
### Correctness & robustness
- ... (source: URL)
### UX & user-facing behavior   — UI-facing stacks
- duplicate-action guard: disable/guard on submit + server idempotency (→ Cross-cutting) ... (source: URL)
### Accessibility (a11y)   — UI stacks
- ... (source: URL)
### Performance   — perf-conscious coding; profiling tools live in docs/verification/performance.md
- ... (source: URL)
### Security   — call-site coding; enforcement in the ops-conventions rule + scanner
- ... (source: URL)
### Maintainability & testability
- ... (source: URL)
### Cross-cutting / integration   — multi-layer / multi-service; contract in docs/sds Integration Points
- idempotency: front guard + server idempotency key; cross-layer consistency ... (source: URL)
### Internationalization / localization   — multi-locale products
- ... (source: URL)
-->

## Anti-patterns (avoid)
{{ANTI_PATTERNS}}
- **Reinventing the wheel**: if a free, commercial-use-OK off-the-shelf solution (official image, standard library, OSS) exists, use it instead of implementing your own.
- **Ephemeral plan indices in comments**: don't reference one-off spec/plan indices (`Step 3`, `Task 11`, `§2.1`) in code comments — comments explain intent, not planning artifacts that go stale and dangle.

## Toolchain / Config
{{TOOLCHAIN_CONFIG}}  <!-- Build, bundle, type-check, lint, test as one set. Based on the output of the official scaffolder for the detected version. Cite sources. -->

## Reuse Candidates (free, commercial-use-OK)
{{REUSE_EXAMPLES}}
