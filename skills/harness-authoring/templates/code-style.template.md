# {{STACK_LABEL}} Code Style

> {{LANGUAGE}} + {{FRAMEWORK_OR_PLATFORM}}. Describe the discipline in prose, **without code snippets**. Sources: {{SOURCES}}

## Naming · Formatting · Imports
{{STYLE_RULES}}

## Best Practices
{{BEST_PRACTICES}}  <!-- Recommended patterns specific to this stack. 1-2 lines each + source. -->

## Anti-patterns (avoid)
{{ANTI_PATTERNS}}
- **Reinventing the wheel**: if a free, commercial-use-OK off-the-shelf solution (official image, standard library, OSS) exists, use it instead of implementing your own.
- **Ephemeral plan indices in comments**: don't reference one-off spec/plan indices (`Step 3`, `Task 11`, `§2.1`) in code comments — comments explain intent, not planning artifacts that go stale and dangle.

## Toolchain / Config
{{TOOLCHAIN_CONFIG}}  <!-- Build, bundle, type-check, lint, test as one set. Based on the output of the official scaffolder for the detected version. Cite sources. -->

## Reuse Candidates (free, commercial-use-OK)
{{REUSE_EXAMPLES}}
