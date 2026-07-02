---
name: task-import
description: Import a Teamer item's context and scaffold the task-doc skeleton (Content filled; Codebase Analysis / Implementation Sequence / Plan left as placeholders). The Teamer-import sub-step /vdev invokes for an ALM task-id entry — not usually invoked directly.
allowed-tools: Bash, Read, Write, Edit
argument-hint: "[task_id]"
---

# /task-import - import Teamer context and scaffold the task file / usage: [task_id]

## Purpose
Import a Teamer item's context and create a skeleton task file — Content filled, analysis and plan left as placeholders for a downstream step to complete.

## Usage
```
/task-import [task_id]
```

## Arguments
- `task_id` : Teamer item id (e.g., DEV-0952). Prompt the user if omitted.

## Execution
1. **자격증명 확인 (keyring)** — Teamer 자격증명은 OS 키체인(keyring)에서 스크립트가 직접 읽는다(평문 파일·모델 컨텍스트 노출 금지). 스킬은 id/pw 를 다루지 않는다. 미설정이면 다음 단계의 `search` 가 안내 메시지를 출력하므로, 사용자에게 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 을 실행하도록 안내하고 중단한다.
2. **Teamer 검색** — `vdev-config.yaml` 의 `teamer.project_no` / `teamer.workitem_no` 를 읽어 스크립트를 직접 호출한다:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" search \
     --project-no <teamer.project_no> --workitem-no <teamer.workitem_no> --text {task_id}
   ```
   출력은 최소 JSON 배열 `[{item_no,item_id,item_title,item_content,status_name}]`. 자격증명 미설정 안내가 출력되면 1단계 안내 후 중단. 결과가 비었으면 사용자에게 알리고 중단.
3. Extract `Item ID`, `Title` and `Content`
4. Use git-branch-manager and pass `Item ID` and `Title`
  - Create branch
  - Checkout branch
  - **IMPORTANT: Branch name and task file name MUST be in English**
  - Branch naming: `feature/{taskid}-{english-title-kebab-case}` (e.g., `feature/DEV-0952-requirement-improvement`)
  - Translate Korean title to concise English kebab-case for branch and file names
  - Obtain `{username}` by running:
    ```bash
    python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" whoami
    ```
    Parse the JSON output `{"username": "..."}` and use the `username` field. The script reads the keyring id and returns the local part (before `@`) — the skill never handles the full id, password, or token.
5. Create the skeleton task file at `docs/tasks/{username}/{taskid}_{title}.md`
  - `{username}`: **keyring id 의 @ 앞부분** — `teamer_api.py whoami` 로 얻는다(스킬은 전체 id/비번을 다루지 않는다). `@` 없는 id 는 전체를 그대로 사용. (e.g., `bsyu@vway.co.kr` → `bsyu`)
  - `{taskid}`: Item ID (e.g., DEV-0952)
  - `{title}`: Title translated to English, converted to kebab-case
  - Create directories automatically if they don't exist
  - Fill only the `## Content` section from Teamer
  - Leave `## Codebase Analysis`, `## Implementation Sequence`, and `## Implementation Plan` as placeholders (the `<!-- TODO -->` markers in the template)
  - Do not analyze the codebase or write a plan — task-import stops after writing the skeleton
  - **Handoff sections**: run `python "${CLAUDE_PLUGIN_ROOT}/scripts/handoff_resolve.py" "${CLAUDE_PROJECT_DIR}/.claude/vway-kit/config/vdev-config.yaml"`. For each kind with `source_mode == "human_doc"`, append a section to the task file:
    ```markdown
    ## Handoff ({Kind})
    **Author:** [작성 주체]
    **Content:**
    <!-- {instruction if present} -->
    ```
    (`{Kind}` = config kind rendered uppercase, e.g. `qa` → `QA`)
    Skip kinds whose `source_mode` is not `human_doc` (AI/AskUserQuestion kinds need no document section).

## Task File Template
File path: `docs/tasks/{username}/{taskid}_{title}.md`

```markdown
# Task: [task_id] - [Title]

## Overview
**Created:** [timestamp]
**Author:** [username]
**Branch:** [branch name]

## Content
[Content from Teamer]

## Codebase Analysis
<!-- TODO: filled by a downstream step. Related existing code, reusable
     components (e.g., shared/common packages), duplication risk areas, and the
     SOLID/DRY application plan go here. -->

## Implementation Sequence
<!-- TODO: filled by a downstream step. Mermaid sequence diagram or flowchart of
     the implementation flow (component interactions, data flow, dependencies). -->

## Implementation Plan
<!-- TODO: filled by a downstream step. The detailed implementation plan. -->

## References
- **Source:** [Teamer Item URL]

<!-- ## Handoff (QA)  ← human_doc 종류가 config 에 있으면 task-import 가 삽입 -->

## Notes
[Additional observations]
```

## Claude Code Integration
- Uses **scripts/teamer_api.py `search`** to fetch the Teamer item context (자격증명은 keyring)
- Uses **git-branch-manager** to create and checkout the feature branch
- Uses **Write** for skeleton task file creation (docs/tasks/{username}/)

## Example Usage
```
/task-import DEV-0952
```

This creates the branch and writes a skeleton `docs/tasks/bsyu/DEV-0952_*.md` (Content filled, analysis/plan as placeholders), then stops.
