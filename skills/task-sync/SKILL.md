---
name: task-sync
description: Summarize the task doc and sync it to the Teamer item via PUT (item_content appended). The final sub-step /vdev invokes after an ALM task-id entry completes — not usually invoked directly.
allowed-tools: Bash, Read, Glob, AskUserQuestion
argument-hint: "[task_id]"
---

# /task-sync - Sync task document summary to Teamer / usage: [task_id]

## Purpose
Read the task document under `docs/tasks/{username}/`, generate handoff content, and update the Teamer item via PUT API.

## Usage
```
/task-sync [task_id]
```

## Arguments
- `task_id` : Task ID (e.g., SDAL-XXXX). Prompt user if omitted.

## Execution

1. **자격증명 확인 (keyring)**
   - Teamer 자격증명은 OS 키체인(keyring)에서 스크립트가 직접 읽는다(평문 파일·모델 컨텍스트 노출 금지). 스킬은 id/pw 를 다루지 않는다.
   - 6·8단계의 스크립트가 미설정 시 안내를 출력하면, 사용자에게 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 을 실행하도록 안내하고 중단한다.

2. **Find task document**
   - If `task_id` not provided, ask user
   - Resolve `{username}` by running:
     ```bash
     python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" whoami
     ```
     Parse the `{"username":"..."}` output and use the `username` field as the directory name.
   - Glob search `docs/tasks/{username}/` for `{task_id}_*.md`
   - If not found, notify user and abort

3. **Resolve handoff kinds**
   - Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/handoff_resolve.py" "${CLAUDE_PROJECT_DIR}/.claude/vway-kit/config/vdev-config.yaml"`
   - Result is a JSON array; each element: `{kind, author, field, source_mode, write_mode, template_path, instruction}`
   - **Backward compat**: if the array is empty (no `handoff` config), fall back to legacy behavior — generate the AI summary using the structure in `templates/handoff/summary.html` and append to `item_content` (same as before).

4. **Generate content per handoff kind**
   For each resolved kind, produce HTML content by `source_mode`:
   - `ai_auto`: AI generates content from the task document. If `template_path` is set, read that file and follow its structure; otherwise apply `instruction`. If **both** are absent (e.g., template file missing so `template_path` is null and no `instruction` configured), warn the user and fall back to a generic task-document summary. (summary kind lands here — `handoff_resolve.py` auto-discovers `templates/handoff/summary.html` as `template_path` even when `template:` is omitted in config, so summary always has a structure to follow.)
   - `ai_guided`: use AskUserQuestion to ask the user for guidance, e.g. "이 handoff 에서 강조할 내용이나 추가 지침을 입력해 주세요." Then AI generates following `template_path`/`instruction` + the guidance. If both `template_path` and `instruction` are absent, warn the user and fall back to a generic task-document summary before applying the guidance.
   - `human_ask`: use AskUserQuestion to collect the content text directly, e.g. "이 handoff ({kind}) 에 들어갈 인수인계 내용을 입력해 주세요." Use the input verbatim.
   - `human_doc`: read the `## Handoff (<Kind>)` section's **Content** from the task document; use it verbatim (from the `**Content:**` line to the next `##` heading or end of file, excluding `**Author:**`). (`<Kind>` is the config kind uppercased, e.g. `qa` → `QA`; match the header case-insensitively.) If the section is missing, warn and skip this kind.
   - `literal`: skip AI/AskUserQuestion/template entirely. Use the resolved `value` verbatim. Replace the token `${today}` with the execution date in `YYYY-MM-DD` format; leave any other text as-is. **Do NOT wrap in the Author marker div** — literal values (dates, flags) must be the raw value so Teamer field types are not broken by markup.
   - Wrap every generated content (ai_auto / ai_guided / human_ask / human_doc — NOT literal) in the author marker `<div>` block with date:
     ```html
     <div style="border-left:3px solid #6c63ff;padding-left:10px;margin:10px 0;">
     <p style="color:#888;font-size:0.85em;">Author: {author} ({YYYY-MM-DD})</p>
     <!-- content here -->
     </div>
     ```
   - If `author` is empty, omit the Author label entirely (do not render `Author:  (date)`).
   - Show a preview of all kinds to the user and ask for confirmation.

5. **Classify by field/write_mode**
   - `field == item_content`: queue for `item_content` (the update script always appends item_content; for an `item_content` replace, the col path is N/A — item_content is append-only at the API layer).
   - else with `write_mode == replace`: write the html/value to a temp file and add `--col-override <field>=<tmpfile>`.
   - else with `write_mode == append`: write the html/value to a temp file and add `--col-append <field>=<tmpfile>`.
   - **Note:** a single field should not be targeted by both replace and append in one sync — if it is, the append (based on the GET original value) takes effect and the replace is discarded.

6. **Teamer 항목 검색**
   - `vdev-config.yaml` 의 `teamer.project_no` / `teamer.workitem_no` 를 읽어 호출:
     ```bash
     python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" search \
       --project-no <project_no> --workitem-no <workitem_no> --text {task_id}
     ```
   - 출력 `[{item_no,item_id,item_title,item_content,status_name}]` 에서 `item_no`·`item_title`·`status_name` 추출.
   - 결과가 여러 개면 사용자에게 선택받는다. 없으면 알리고 중단.
   - **필드 보존·item_content append 는 8단계의 `update` 스크립트가 내부에서 수행한다**(스킬은 보존 로직을 다루지 않는다).

7. **Determine workflow status**
   - If current `status_name` is "진행" (Progress): auto-set to "검토" (Review) — pass `--target-status-name 검토` to the update script (8단계) which resolves the actual status_no via workflow API.
   - Otherwise: show current status to user and ask whether to change

8. **Teamer 항목 업데이트**
   - 생성한 본문(append 대상)은 임시 파일에 쓰고, 각 col override 도 임시 파일로 쓴 뒤 스크립트를 호출한다:
     ```bash
     python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" update \
       --project-no <project_no> --workitem-no <workitem_no> \
       --item-no <item_no> --searchtext {task_id} \
       --content-file <tmp_content.html> \
       [--col-override col22=<tmp_col22.html> ...] \
       [--col-append col33=<tmp_col33.html> ...] \
       [--target-status-name 검토 --workflow-no <teamer.workflow_no>]
     ```
   - `update` 가 내부에서 GET→non-null colXX 보존→item_content append→(target-status-name 있으면)status 해석→multipart PUT 을 수행한다.
   - 출력 `{item_id,item_title,item_workflow_status_no,mode}` 로 성공을 사용자에게 보고한다. 자격증명 미설정 안내가 출력되면 1단계 안내 후 중단.

## API Notes

- PUT uses **`multipart/form-data`** format (`itemVO.xxx` field names)
- **Non-ASCII encoding**: `teamer_api.py` 가 Python `urllib` 로 UTF-8 multipart 바디를 직접 만들어 보낸다(curl/Node 불필요).
- Auth: `Authorization: Bearer {token}` header + `Cookie: Admin-Token={token}` both required
- **Field preservation required**: omitted fields reset to null on PUT. Always include non-null fields from GET (especially `colXX` date/status fields)

## Summary HTML Structure

The AI summary (summary kind, `ai_auto`) follows the structure defined in `templates/handoff/summary.html` — that file is the SSOT for the 3-section HTML template (Implementation / Verification / Notes) and all authoring rules (atomic `<li>`, self-contained bullet, summarize-not-enumerate, language convention, etc.).

## Example Usage
```
/task-sync SDAL-XXXX
```

This command will:
1. Find and read `docs/tasks/{username}/SDAL-XXXX_*.md`
2. Resolve handoff kinds and generate content per kind; show preview for confirmation
3. Search Teamer for SDAL-XXXX item to get item_no
4. PUT update item_content (and col_overrides if set) via multipart/form-data
