# Memory consolidation / SSOT migration discipline (SSOT)

The **authoritative discipline** that `/harness-insight` Step 5 follows. It reviews the accumulated project memory and
(1) **prunes** invalid/duplicate entries, (2) **promotes** lasting knowledge to the project's `.claude/rules/`/`docs/`,
and (3) **keeps** cross-project habits in memory.
**Destructive actions (pruning/migration) only after user approval.** Change this discipline only in this file.

Project-agnostic — derive the memory path, document format, and language **from the target project**
(do not hardcode them or invent them from model knowledge).

---

## 1. Data sources

- Memory location: `<project_dir>/memory/` — `<project_dir>` is the **base project directory** that the Step 2 script
  printed as `scanning <dir>` (the cwd slug; excluding worktree siblings).
  That is, `~/.claude/projects/<slug>/memory/`.
- Structure: `MEMORY.md` (index — one line = one memory) + each `*.md` (frontmatter + body).
- frontmatter `metadata.type`: `user` | `feedback` | `project` | `reference`.
- If the memory directory is missing or empty, **skip** Step 5 (nothing to consolidate — report only).
- Local file reads only — memory content never leaves the machine.

## 2. Classification (each memory → one)

- **prune** — invalid/wrong, superseded by a higher-level document, valid only for a specific past conversation,
  **already recorded by the repo** (code, git history, CLAUDE.md, existing docs), or the original after promotion is complete.
- **promote** — lasting `project`/`reference` knowledge that should be version-controlled and team-shared
  (architecture, design decisions, operational pitfalls, conventions, external resources). Target selection is §3, authoring is §4.
- **keep** — **cross-project / personal habits/preferences** among `user`/`feedback`
  (those that do not fit a specific repo's docs). Do not touch them.

  > Decision criterion: **"is this knowledge about handling this repository?"** (→ promote) vs
  > **"is this about how to work with this person?"** (→ keep). The latter belongs in memory.

## 3. Promotion target: rules vs docs

**Prefer conventions that actually exist** in the project (only those confirmed in Step 3).

- **`.claude/rules/`** (or the project's `rules/`) — **always-apply discipline the model must follow on every task**:
  coding standards, commit discipline, prohibitions, policy.
- **`docs/`** — **reference knowledge**: architecture, design decisions, operational runbooks, pitfalls, troubleshooting, external links.
- If only one of them exists, use that one. If both exist, split by nature (discipline → rules, reference → docs).
- If neither exists, create a new `docs/` or confirm the location with the user.

## 4. Promotion authoring discipline (per the target project)

1. **Check format/language** — **read the existing documents** in the target rules/docs first and match the header style,
   language (Korean/English), tone, and path conventions. Do not invent the format from model knowledge.
2. **Keep the essentials, be concise** — compress the memory's Why/How down to **the essentials only**. Reduce verbose
   incident narratives to one or two lines of rule/rationale.
3. **Follow SSOT (no duplication)** — if the same fact already exists in an existing document, **merge/link instead of
   creating a new file**. Create a new file only when it does not exist. Keep one value (version/path/policy) in one place only
   and defer the rest with links.
4. **point-in-time verification** — if the memory cites a `file:line`, symbol, or flag, promote it **only after confirming
   its existence against the current code** (do not enshrine a stale citation as fact). Drop the parts that cannot be confirmed.

## 5. Application (user approval gate)

1. **Present a proposal table into the conversation** — columns: `memory | classification (prune/promote/keep) | target SSOT | rationale`.
   Include keep items in the table as "keep" too, stating why they are not promoted.
2. **Apply only after approval** — after confirming via `AskUserQuestion` or similar:
   - (a) promote: write to the target rules/docs per the §4 discipline (**prefer merging** into existing documents).
   - (b) prune: remove prune items + the original memory files whose promotion is complete.
   - (c) update the `MEMORY.md` index — remove pruned/promoted lines, leaving **only kept items**.
3. No deleting/moving/overwriting without approval. **Partial approval** (applying only some) is supported too.

---

## Critical

1. **Approval gate mandatory** — memory pruning/migration is destructive. Do not break the propose → approve → apply order.
2. **Keep items are inviolable** — the keep classification is not pruned or migrated.
3. **No SSOT duplication** — if it already exists in a document, merge/link; do not spawn new files gratuitously.
4. **Target paths** — writes go only to the **host project's** rules/docs and `<project_dir>/memory/`.
   Do not write to the plugin directory.
5. **Local processing only** — memory content never leaves the machine.
