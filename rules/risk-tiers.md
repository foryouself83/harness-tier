# Risk-Tiered Workflow

The tier decides which skills run and which gates the commit hook enforces. Branch names are
`flow-config.branches` keys — roles such as integration→dev, never literal branch names.

## Principle

Higher tier = more skills engaged + more mandatory gates; the *depth* of
process the verdict selects is what varies. When the tier is ambiguous,
`/flow` escalates one tier (bias to safety).

**Enter `/flow` (via the Skill tool) as your FIRST action** on any code
change, feature, fix, or development request — *before* reading code,
planning, or editing. You do not judge the tier on your own and proceed:
`/flow` runs the classification, confirms the tier with the user, and
writes the marker the commit gate reads. Skipping `/flow` leaves the commit
**unclassified**, and the commit gate **blocks it** (fail-closed — a commit
with no tier marker is refused; see Hard gates). If the workflow is
genuinely unwanted, the user removes the gate with `/flow-uninstall` — you
never work around it.

## Gates (glossary)

- **Runtime** — the commit hook runs them, no marker: `precommit` (changed modules'
  every-commit checks), `security-scan` (all modules' promotion checks), `wiki`, `doc-style`
  (warns only).
- **Marker** — `<gate>.done`, recorded only after the work passes: `review`, `doc-sync`
  (/doc-sync), `bump` (Staging), `security` (Release).

Detail: [`gate-mechanics.md`](gate-mechanics.md), [`promotion.md`](promotion.md).

## Step 1 — Classify the task (Docs or Dev)

**Code, or no code.**

- **Docs** — only `.md`, narrative content, comments/docstrings or pure config-text, in a single
  service, with no contract, schema or dependency change.
- **Dev** — any one of: a source-code change however small (`.py` / `.js` / `.ts` …, a
  migration, shell logic); a new feature, endpoint or requirement change; a DB schema change; a
  cross-service shared package; business logic, core nodes, validators or workflow
  orchestration; a dependency change; 2+ services.

When in doubt, escalate one tier; criteria spanning tiers take the highest. A promotion request
goes to `/release-commit`, never `/flow`.

## When each tier applies (git-flow mapping)

| Tier | `superpowers` | Moment | Gates |
|------|---------------|--------|-------|
| **Docs** | OFF | `feature/*` / `fix/*` → integration, no code | doc-sync, wiki, doc-style |
| **Dev** | ON | `feature/*` / `fix/*` → integration, any code | precommit, review, doc-sync, wiki, doc-style |
| **Staging** | OFF | integration → staging (rc cut) | precommit, review, security-scan, bump, wiki, doc-style |
| **Release** | OFF | staging → production, or prod deploy | precommit, security-scan, security, wiki, doc-style |

An irreversible, prod-critical or security change on a feature branch is Dev, plus
`/security-review` as an unenforced step. Dev requires the `superpowers` plugin
(`superpowers@claude-plugins-official`); without it `/flow` stops and asks the user to install it.

## Hard gates (enforced mechanically)

`/flow` and `/release-commit` record `tier` (`<tier>:<branch>`) and `<gate>.done` under
`.claude/harness-tier/.flow/`. The `git commit` hook blocks a commit missing a required marker or
the `tier` marker; on the staging or production branch it enforces that promotion's gates.
Deploy commands are not gated. Every commit goes through `/commit`; never `--no-verify`.
