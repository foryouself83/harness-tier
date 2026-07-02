---
name: harness-insight
description: Aggregates Claude Code activity over a given period into a 4-section report of development/harness insights, output into the conversation, then reviews the accumulated project memory and consolidates it (prune / migrate to SSOT). From the transcript (prompts sent and tool_use) it derives the distribution of work done, repeated instructions (harness candidates), activity hotspots, and next actions; for memory it prunes invalid/duplicate entries, promotes lasting knowledge to .claude/rules or docs/, and keeps cross-project habits (pruning/migration only after user approval). It does not create a report file (intermediate txt files are deleted after the work). Use for requests like "insights for the last N days/weeks", "summarize what I did this week", "pull out harness candidates", "clean up memory".
argument-hint: "period (e.g., 7 days, 2 weeks, 30 days — default 7 days)"
allowed-tools: Bash, Read, Glob, Grep, Edit, Write, AskUserQuestion
---

# Harness-Insight — Period-based Development/Harness Insights

Aggregates the Claude Code transcript of the target project (the cwd from which this skill was invoked) and **outputs a
4-section insight report into the conversation** (Step 4), then reviews and **consolidates the accumulated
project memory** (Step 5). **It does not create a report file (.md).** It creates **only intermediate artifacts for the
report (two txt files), temporarily**, and deletes them once output is done. However, Step 5, after user approval, writes to
the target project's `rules/`/`docs/` and consolidates memory (this is not a report artifact but an SSOT update/
consolidation — a different nature). Project-agnostic — it works in any repository (command groups, hotspots,
memory paths, and document formats are derived from the data / target project).

## Paths
```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
TMP="$(mktemp -d 2>/dev/null || echo "${ROOT}/.harness-insight-tmp")"   # intermediate artifacts (deleted after the work)
```
Write intermediate txt only to the temporary directory (do not pollute the project root). Do not write to the plugin directory.

## Step 1 — Parse the period
Convert the argument (`$ARGUMENTS`) to **days**. If there is no argument, **7**.
- `N일`/`N day(s)` → N · `N주`/`N week(s)` → N×7 · `N개월`/`N month(s)` → N×30 · `오늘`/`today` → 1
- If only a number is given, treat it as days. If ambiguous, use 7 and state the assumed period at the top of the report.

## Step 2 — Aggregation (script, generates intermediate artifacts)
```bash
python3 "${PLUGIN}/scripts/harness_insight.py" --days <DAYS> --out-dir "${TMP}"
```
Creates two files in the temporary directory:
- `prompts.txt` — the user prompts I sent (intent, noise removed)
- `activity.txt` — the actual tool_use aggregation (session/prompt counts, tool distribution, top commands, hotspot directories/files)

If it exits with `no project dir found`, the cwd is a project that has never been worked on with Claude Code —
notify the user and stop (no guessing).

> **Data sources / extraction rules = [`references/transcript-data.md`](references/transcript-data.md)** —
> the JSONL location/schema, noise filters, command normalization/hotspot derivation, and period filter are pinned there.
> If extraction breaks (e.g., a transcript format change), verify and update this reference as the SSOT.

## Step 3 — Read
1. `Read` **both** `${TMP}/prompts.txt` · `${TMP}/activity.txt`.
2. To make the "(existing)" determination in section 2, check the project's existing harness (only what exists):
   `Read ${ROOT}/CLAUDE.md` · `Glob ${ROOT}/{rules,.claude/rules}/**/*.md` ·
   `Glob ${ROOT}/{agents,.claude/agents}/**/*.md` · `Glob ${ROOT}/{skills,.claude/skills}/**/SKILL.md` ·
   `Glob ${ROOT}/.claude/commands/**/*.md`. If none, exclude that component kind from the candidate pin locations.
   The existence of `rules/`/`.claude/rules/`/`docs/` confirmed here is also used to decide Step 5 promotion targets.
3. For Step 5 (memory consolidation), read the project memory: under the `memory/` subdirectory of the base project
   directory (the path corresponding to the cwd slug among those Step 2 printed as `scanning <dir>`) —
   `Read <project_dir>/memory/MEMORY.md` · `Glob <project_dir>/memory/*.md`, then `Read` each file.
   If the memory directory is missing or empty, skip Step 5.

## Step 4 — Report authoring (output into the conversation — no file created)
Based **only on the two txt files**, output exactly the 4-section report in English **directly into the conversation**.
Do not save it as a file like `<ISO-week>.md`.

> **Format / authoring discipline / examples = [`references/report-format.md`](references/report-format.md)** (SSOT).
> The template skeleton and a filled example are there — change the format in the reference, not in this SKILL copy.

Execution summary (details in the reference):
- Sections = `1. Distribution of work done` / `2. Harness candidates` (only those repeated 2+ times, in a 4-column table: repeated instruction · frequency · pin location · resolution;
  items existing from Step 3 marked "(existing)") / `3. Activity hotspots` (commands · directories/files · tool ratios + "Interpretation:") /
  `4. Recommendations for next week` (3–5 actions derived from 2 and 3).
- **No emoji · no evaluative language** (do not grade right/wrong) · **omit if not in the data** (no guessing).

## Step 5 — Memory consolidation (review → approve → apply)
Review the project memory read in Step 3, classify it into **prune / promote to SSOT / keep**,
and **after user approval** apply promotion (→ project `rules/`/`docs/`), pruning, and `MEMORY.md`
index updates. If there is no memory, skip.

> **Classification / target / authoring / approval discipline = [`references/memory-consolidation.md`](references/memory-consolidation.md)** (SSOT).
> The rules vs docs criteria, the promotion authoring method (format/language check · concise · no duplication · point-in-time verification),
> and the approval gate are pinned there — change the discipline in the reference, not in this SKILL copy.

Execution summary (details in the reference):
- Classify each memory: **prune** (invalid/duplicate/already recorded by the repo) · **promote** (lasting project/
  reference knowledge → always-apply discipline to `rules/`, reference material to `docs/`) · **keep** (cross-project/
  personal-habit user/feedback — leave untouched).
- Present a **proposal table** (`memory | classification | target SSOT | rationale`) into the conversation first, and get
  approval via `AskUserQuestion`. **No pruning/migration without approval** (partial approval supported).
- Promotion checks the target project's **existing document format/language** and keeps only the essentials, concisely,
  **preferring to merge into existing documents** (no duplication). After applying, delete the original memory + leave only the kept items in `MEMORY.md`.

## Step 6 — Delete intermediate artifacts (mandatory)
Once the report and memory consolidation are done, delete the intermediate artifacts. Do not leave temporary artifacts (txt) behind.
```bash
rm -rf "${TMP}"
```

## Critical rules
1. **No report file created** — the report (`<ISO-week>.md`, etc.) is conversation-only. The only file writes are Step 5's
   SSOT promotion (rules/docs) and memory consolidation, and even those happen **only after user approval**.
2. **Delete intermediate txt after the work** — always perform Step 6.
3. **The report is based only on the two txt files** — do not fabricate anything not in the data; omit it (Step 4).
4. **No emoji / no evaluative language** — facts, frequencies, patterns, actions only (report).
5. **The memory consolidation approval gate is mandatory** — pruning/migration is destructive. Follow the propose → approve → apply order,
   leave keep items untouched, and promote without duplicating existing documents (Step 5, reference).
6. The host is `${CLAUDE_PROJECT_DIR}`; read the plugin from `${CLAUDE_PLUGIN_ROOT}`. Writes go only to the host
   project (rules/docs) and `<project_dir>/memory/` — do not write to the plugin directory.
7. Local processing only — transcript/memory data never leaves the machine.
