# Transcript Data Contract (SSOT that harness_insight.py depends on)

The **data sources and schema** from which `scripts/harness_insight.py` extracts prompts/activity.
This format is owned by Claude Code (not an external package — parsed with the standard library only), and
the points where extraction could break if the format changes are pinned here. Verify and update the format against the
**actual `*.jsonl` as SSOT**, not model knowledge.

---

## 1. Location

```
~/.claude/projects/<slug>/<sessionId>.jsonl
```

- `<slug>` = the cwd absolute path with non-alphanumeric characters replaced by `-`
  (`re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())`).
- A **git worktree** has a different file path → it is stored in a different `<slug>` directory. Because worktree slugs
  **share the main repo's slug as a prefix**, gather them together with a `<slug>*` prefix glob
  (`project_dirs_from_cwd`). Side effect: a *sibling project* whose slug overlaps as a prefix (like `myapp-v2`) may also
  match, so `main` prints the collected directories to make this visible.
- No external leakage — all processing is local file reads only.

## 2. Record structure (JSON Lines — one line = one record)

Each line is an independent JSON object. Corrupt lines are skipped (`json.JSONDecodeError` ignored). Corrupt bytes are
leniently decoded with `errors="replace"` so that a single-line error does not abort the whole weekly collection.

Common top-level keys (only those used for extraction):

| Key | Meaning | Extraction use |
|---|---|---|
| `type` | record kind | only `user`/`assistant` are processed; the rest are ignored |
| `timestamp` | ISO8601 (`...Z`) | period filter (cutoff). Missing/unparseable → conservatively excluded |
| `sessionId` | session identifier | session count |
| `message` | message body | `content` is extracted from here |

> **Note**: `type` mixes in many kinds that have no message — `attachment` · `queue-operation` ·
> `file-history-snapshot` · `last-prompt` · `ai-title` · `system`. These have no `message`, so they are
> filtered out in one shot by the `type in (user, assistant)` gate (safe even if the schema adds kinds).

## 3. user records → prompt extraction

`message.content` can be **either a string or a list of blocks** (`user_text` handles both).

- String: use as-is.
- List: concatenate only the `text` of `type == "text"` blocks. Other blocks such as `tool_result` are ignored
  (so tool return values do not pollute the prompts).

**Noise removal** — text injected by the harness is not a genuine user prompt, so filter it by prefix
(`NOISE_PREFIXES`): `<ide_` · `<system-reminder` · `<command` · `<local-command` ·
`<task-` · `<user-` · `[Request interrupted` · `Caveat:`.
→ When a new injection marker appears, this list must be extended to keep aggregation accuracy.

## 4. assistant records → activity extraction

`message.content` is a list of blocks. Only `type == "tool_use"` blocks are aggregated (`thinking`/`text` ignored).

| Block field | Aggregation |
|---|---|
| `name` | tool distribution (`tool_use distribution`) |
| `name ∈ {Edit, Write, NotebookEdit}` + `input.file_path` | file basename frequency + directory hotspots |
| `name ∈ {Bash, PowerShell}` + `input.command` | split compound commands, then normalize/count each segment |

- **Compound command splitting** (`normalize_cmds`): split commands chained on one line (`cd x && git commit`, `a; b`,
  `a || b`) by `&&`/`||`/`;` and **count each segment separately** (counting only the first token would let navigation
  like `cd` pollute the hotspots). Pure shell builtins (`cd` · `export` · `set` · `source`, etc.) and empty
  segments are excluded since they are not "command execution". Pipes (`|`) are not split (a single pipeline).
- **Segment normalization** (`normalize_cmd`, project-agnostic): skip leading `VAR=val` env assignments
  (`^\w+=`) → executable basename (`/usr/bin/python3` → `python3`) → for `SUBCOMMAND_TOOLS`
  (git · docker · uv, etc.) keep one non-flag subtoken (`git commit`). Unregistered tools are also grouped
  normally by basename.
- **Directory hotspots** (`hotspot_dir`, project-agnostic): the **last 2 segments** of the file path's parent directory
  (`.../src/api/x.py` → `src/api`). The drive prefix (`c:`) is removed. Derived from the data rather than a fixed regex so hotspots
  surface even without knowing the project root.

## 5. Period filter (2-stage)

1. **mtime pre-filter**: `*.jsonl` last modified before the cutoff are excluded early (avoiding a full re-read of the
   entire accumulated history). Safe because mtime is updated when new records are added.
2. **Record ts filter**: each record's `timestamp` is re-compared against the cutoff (boundary refinement). Records with
   unknown dates are excluded to prevent inflating the aggregation.

## 6. Dependencies

Standard library only: `argparse` · `glob` · `json` · `os` · `re` · `collections.Counter` · `datetime`.
No extra installation needed (runs in any project environment as long as `python3` is present). The input is only the above JSONL that Claude Code
records — no separate API/DB/network dependency.
