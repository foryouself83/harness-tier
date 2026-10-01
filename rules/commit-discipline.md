# Commit Discipline

Applies to every `git commit -m` and every merge message. [`/commit`](../skills/commit/SKILL.md)
carries out the mechanics — staging, the type choice, the length check — and reads this
file for every rule it applies.

## Message format (Conventional Commits)

```
<type>[(scope)][!]: <description>
                                   ← blank line
[body]
                                   ← blank line
[footer(s)]
```

- **Subject** — `type(scope): description`; ≤50 chars (non-ASCII = 1
  each); lowercase, imperative; no trailing period. Over 50 →
  **REWRITE**, no exceptions.
- **Body** — what & why as `-` bullets, **one sentence each**, not
  prose; each line ≤72, wrap at word boundaries. Fragments over
  sentences (noun phrases + `cause → effect`). Never prefix a bullet
  with `feat:`/`fix:` — the subject owns the type. Drop anything that
  restates another bullet, and anything the reader need not know.
- **No history narration in the body** — no before-and-after, no
  migration note, no account of what an earlier round of the same
  work did. The commit *is* the history entry.
- **Footer** — `BREAKING CHANGE: …`, `Refs: #123`; same ≤72.

Subject/body limits (the **50/72 rule**) + no-trailing-period are
lint-enforced; bullets, fragments, and terseness are soft style.

Example:

```
feat(auth): rotate refresh tokens per use

- Old tokens: 15-min re-login churn.
- Per-use rotation → replayed tokens rejected.

BREAKING CHANGE: refresh tokens now single-use.
Refs: #421
```

## Language

`type`/`scope`/`BREAKING CHANGE` keywords stay English (spec format —
`semantic-release`/`gitlint` parse them). The `<description>` and body
follow the host's configured response language (e.g. a `CLAUDE.md`
language directive); default to English if unset.

## Commit type → version impact

| Type | Version | When |
|------|---------|------|
| `feat` | MINOR | New feature |
| `fix` / `perf` | PATCH | Bug fix / perf improvement |
| `docs` / `chore` / `refactor` / `test` / `style` / `ci` / `build` | none | No release |
| `BREAKING CHANGE:` in footer | MAJOR | Incompatible change |

**Squash** merges pick the **highest-priority type** among bundled
commits.

## When asked "is this commit compliant?"

Re-measure subject char count and each body line length yourself.
Don't trust your earlier write.
