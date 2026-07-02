# harness-insight report format (SSOT)

The **authoritative format** that `/harness-insight` Step 4 follows. Change the format only in this file
(the SKILL.md body is an execution summary — this file wins on conflict).

The report is written **based only on the two temporary txt files (`prompts.txt` · `activity.txt`)** and **output into the conversation**.
It is not saved as a file (no `<ISO-week>.md`, etc.).

---

## Authoring discipline (enforced)

1. **No emoji** — do not use it anywhere in the title or body.
2. **No evaluative language** — do not grade prompts/actions as right or wrong (no "good habit" · "struggled" · "did well" ·
   "inefficient", etc.). Write only **facts, frequencies, patterns** and the **actions** derived from them.
3. **Data-limited** — do not fabricate anything not in the two txt files; omit it. Quote numbers exactly as the `activity.txt`
   values.
4. **Exactly 4 sections** — keep the skeleton below (no adding/removing sections).

---

## Template (skeleton)

```markdown
# Development Insights — <project name> (last <DAYS> days)
**<period start>~<period end> · <N> sessions · <M> prompts**   (N·M quote activity.txt's sessions·prompts)

## 1. Distribution of work done
- List the topics from prompts.txt as 4–6 clusters, ordered by weight.
- Each line is "area: specific content". Put the highest-weight items at the top.

## 2. Harness candidates
- Include only instructions of the same intent repeated 2 or more times (exclude one-offs).
- Pin location = the place among CLAUDE.md / rules / agents / skills / commands that would make the repeated instruction
  disappear (only kinds that exist in the project — those confirmed in Step 3).
- For items already present in the existing harness, mark "(existing)" in the pin location and write only the new increment in the resolution.
- The environment's "current state/history" (server/infra status, etc.) is not in scope for this skill and is not covered.
- Write only as the 4-column table below:

| Repeated instruction | Frequency | Pin location | Resolution |
|---|---|---|---|
| … | … times | … | … |

## 3. Activity hotspots
- Based on activity.txt, one line each:
  - Top commands run most often (frequency) — `## top commands`
  - Top directories/files edited most often (frequency) — `## most-edited directories` / `## most-edited files`
  - Tool ratios (Bash · Read · Edit, etc.) — `## tool_use distribution`
- Then, with "Interpretation:", 2–3 facts read only from the numbers above. Do not write interpretations with no numerical basis.

## 4. Recommendations for next week
- 3–5 concrete actions derived directly from sections 2 and 3.
- Each line is in the form "actionable operation + target file/location".
```

---

## Example (filled form — for format reference; numbers are fictional)

```markdown
# Development Insights — myapp (last 7 days)
**2026-06-23~2026-06-30 · 18 sessions · 142 prompts**

## 1. Distribution of work done
- Auth: OAuth token expiry handling · refresh flow debugging
- API: added pagination to the /orders endpoint, tidied the response schema
- Tests: restructured pytest fixtures, adjusted the coverage gate
- Docs: updated the README setup procedure

## 2. Harness candidates

| Repeated instruction | Frequency | Pin location | Resolution |
|---|---|---|---|
| "Use conventional commits for commit messages" | 5 times | CLAUDE.md | State the commit convention in 1 line |
| "Respond in Korean" | 4 times | CLAUDE.md (existing) | — |
| "Write tests first" | 3 times | rules/tdd.md | Create a new TDD rule |

## 3. Activity hotspots
- Commands run most often: pytest(31) · git add(22) · ruff check(14)
- Locations edited most often: src/api(27) · tests(19) · routes.py(11)
- Tool ratios: Read 34% · Edit 28% · Bash 22% · Grep 9%
- Interpretation: The Bash-to-Edit ratio is high, so manual verification loops are frequent. The tests directory is edited at
  70% of src/api's frequency, so tests accompany each change.

## 4. Recommendations for next week
- Add the conventional commits rule to CLAUDE.md in 1 line (removes 5 repeated instructions)
- Create a new TDD rule at rules/tdd.md (removes 3 repeated instructions)
- Reinforce integration tests for the src/api hotspot (tests/api/)
```
