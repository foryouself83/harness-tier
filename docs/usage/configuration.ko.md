# 설정

[English](configuration.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

`.claude/harness-tier/config/` 아래 두 파일이 하네스 동작을 결정함: 사용자가 편집하는
`flow-config.yaml`, 편집하지 않는 `flow-tiers.yaml`.

## `flow-config.yaml` — 저장소별 값

`/flow-init` 이 생성함. git 추적 대상이라 저장소를 공유하는 모두가 같은 설정을 씀. 슬롯 각각에
주석이 달린 전체 템플릿은 [`flow-config.example.yaml`](../../flow-config.example.yaml) 참고.
핵심부:

```yaml
branches:
  integration: dev           # 기능 작업이 합쳐지는 곳
  staging: stage             # QA / 릴리스 후보 브랜치
  production: main           # 프로덕션 릴리스 브랜치

merge_workflow:
  pull_request: []           # PR 로 보낼 흐름; [] = 모든 흐름이 직접 머지

modules:                     # 모듈별 사전검사
  - name: api
    path: services/api/      # 이 경로 아래 파일이 바뀌면 이 모듈의 검사를 실행
    checks:
      lint:        "ruff check services/api"
      static:      "uv run pyright services/api"
      import_lint: "uv run lint-imports --config services/api/.importlinter"
      test:        "uv run pytest services/api"
      security:    "uv run bandit -r services/api"

review_checklist:            # Dev 리뷰 게이트가 변경 파일마다 판단하는 기준
  - "regression tests pass"
  - "cross-service contract validity"
  - "DB transaction & migration safety"
  - "async task idempotency & queue routing"
  - "API error conventions"

commit_guide: docs/operations/commit-versioning-guide.md   # 있으면 /commit 이 읽음

gate_evidence:
  invalidate_on_edit: true   # false 면 편집이 review/doc-sync 증거를 더는 무효화하지 않음

doc_sync:                    # /doc-sync 가 맞추는 대상
  index: CLAUDE.md
  dirs:
    - "docs/"
    - ".claude/rules/"
  service_docs: "services/*/CLAUDE.md"
```

### `branches`

세 키가 브랜치명을 정함. 브랜치 흐름 규칙은 작업 브랜치를 고정 접두사 —
`feature/*`·`fix/*`·`hotfix/*` — 로 매칭하며, 이 접두사는 설정할 수 없음.

### `merge_workflow.pull_request`

로컬 `git merge` 대신 PR 을 거치는 흐름:

- `daily` — `feature/*`·`fix/*` → integration;
- `promotion` — integration → staging, staging → production, 그리고 `hotfix/*` → production.

비워 두면(기본값) 모든 흐름이 직접 머지로 남음. 커밋 규율은 어느 쪽이든 그대로 — 머지만
바뀜. PR 로 간 흐름이 잃는 것과 그 대체는
[PR 워크플로와 브랜치 룰셋](promotion-and-release.ko.md#pr-워크플로와-브랜치-룰셋) 참고.

### `modules` 와 `checks`

파일은 `path` 가 자신의 접두사인 첫 모듈에 속함. `path: ""` 는 모든 파일에 매칭 — 단일
스택 저장소를 모듈 하나로 표현하는 방법. 어느 모듈에도 걸리지 않은 파일은 사전검사를
건너뛰고, 차단 시 게이트가 목록으로 알려줌.

`checks` 의 각 키는 검사 하나. 값은 명령 문자열이거나 `{ run: <cmd>, when: … }`.
`lint`·`static`·`import_lint`·`test`·`security` 외에 원하는 키를 자유롭게 추가할 수 있음
(license, sbom, secret-scan 등). 필드명은 `on` 이 아니라 `when` — YAML 은 맨 `on` 키를
불리언으로 읽으며, 검사 키 이름을 `off`·`yes`·`no`·`true`·`false` 로 지어도 같은 문제가 생김.

| `when` | 게이트 | 범위 | 실행 시점 |
|--------|--------|------|-----------|
| `every-commit`(`security` 를 제외한 모든 문자열 값의 기본값) | `precommit` | 변경된 모듈 | Dev·Staging·Release 커밋 |
| `promotion`(문자열 `security` 의 기본값) | `security-scan` | 전체 모듈 | Staging·Release 커밋 |

시점은 해당 게이트가 그 등급에 있을 때만 실행되므로, Docs 커밋에서는 모듈 검사가 전혀
돌지 않음. 알 수 없는 `when` 값은 경고와 함께 `every-commit` 으로 읽힘. 명령은 커밋 훅
안에서 실행됨 — [게이트가 보는 것](tiers-and-gates.ko.md#게이트가-보는-것) 참고.

### `review_checklist`

Dev `review` 게이트가 변경된 모든 파일을 판단하는 기준. 위 다섯 항목은
[`rules/risk-tiers.md`](../../rules/risk-tiers.md) Step 3 에서 옴 — 하나를 빼는 대신 자신의
항목을 덧붙임.

### `commit_guide`

`/harness-init` 이 생성하는 자신의 커밋·버전 관리 문서. `/commit` 은 이 문서의 프로젝트별
사실(scope 어휘, 0.x 정책, 릴리스 도구가 `Release-Level` 트레일러를 읽는지)을 우선함. 파일이
없으면 `/commit` 은 `risk-tiers.md` 만으로 동작함.

### `gate_evidence.invalidate_on_edit`

`true`(기본값)면 편집 한 번이 `review`·`doc-sync` 증거를 모두 무효화함 — 리뷰가 요청한 수정도
포함. `false` 면 통과 이후의 편집이 그 리뷰가 보지 못한 채로 커밋됨. 자세한 내용은
[게이트 증거](tiers-and-gates.ko.md#게이트-증거) 참고.

### `doc_sync`

[`/doc-sync`](daily-work.ko.md#doc-sync--문서를-맞춰-둠) 가 맞추는 문서: `index` 파일,
`dirs` 글롭, 모듈별 `service_docs` 글롭.

### `wiki`

[`/wiki-init`](project-harness.ko.md#wiki-init--문서를-지식-그래프로) 이 씀.
`enable: false` 이거나 섹션 자체가 없으면 `wiki` 게이트는 아무것도 하지 않음.

| 슬롯 | 의미 |
|------|------|
| `enable` | `wiki` 게이트를 켬 |
| `root` | 위키 루트, 기본 `docs/` |
| `index` | 그래프 진입점, 고아 판정의 기준선 |
| `max_lines` | 파일 하나-개념 하나 크기 경고, `0` 이면 끔 |
| `context_lines` | `wiki_graph.py --neighbors` 기본 줄 예산 |
| `defect_rule_threshold` | 같은 태그가 이 횟수만큼 뜨면 규칙 승격 경고, `0` 이면 끔 |

### `doc_style`

[`rules/doc-style.md`](../../rules/doc-style.md) 에 대한 문체 검사.

| 슬롯 | 의미 |
|------|------|
| `enable` | 커밋 시점 검사와 `doc-style.yml` 워크플로를 함께 켬 |
| `paths` | 범위에 넣을 저장소 상대 글롭, 기본 `["**/*.md"]`; 주석·docstring 을 포함하려면 `**/*.py`·`**/*.sh` 추가 |
| `exclude` | 범위에서 뺄 글롭, 검사기가 항상 빼는 세 가지에 더해짐 |

검사기는 `CHANGELOG.md`, `docs/superpowers/`, `.superpowers/` 를 항상 건너뜀; `exclude` 는
여기에 더할 뿐 뺄 수는 없음. `/flow-init` 이 이 섹션을 물음.

### `design_docs`

여섯 [설계 산출물 스킬](design-docs.ko.md) 이 읽음.

| 슬롯 | 기본값 | 의미 |
|------|--------|------|
| `templates` | `.claude/harness-tier/templates/design-docs` | `<doc>.template.md` 파일 위치; `/flow-init` 이 최초 1회 시딩하고 이후 절대 덮어쓰지 않음 |
| `docs` | `docs/deliverables` | 작성형 스킬(아키텍처·API·ERD·테이블)이 `<doc>.md` 를 쓰는 위치 — SRS·SDS 는 `docs/srs/`·`docs/sds/` 에 그대로 남음 |
| `output` | `docs/deliverables/results` | `<doc>.docx` 가 렌더링되는 위치 |
| `renderer` | `https://kroki.io` | `mermaid`·`d2` 도식 블록을 전송해 SVG로 렌더받는 곳 — 자체 호스팅 Kroki를 가리키면 도식 원본이 공개 서비스 밖으로 나가지 않음 |
| `base_docx` | `null` | 렌더가 스타일을 재사용할 회사 `.docx` 양식; `null` 이면 `python-docx` 기본 스타일 사용 |
| `gitignore_output` | `false` | `true` 면 `/flow-init` 이 `output` 을 `.gitignore` 에 추가 |

### CI 섹션

`contract_test`·`unit_test`·`e2e`·`versioning` 은 각각 GitHub Actions 워크플로를 렌더링하고,
`deploy` 는 배포 워크플로를 렌더링함. 각 슬롯과 플래그가 켜는 것은
[CI 워크플로](ci-workflows.ko.md) 와 [배포](deployments.ko.md#deploy-블록) 참고.

## `flow-tiers.yaml` — 등급 정책(편집 금지)

`flow-config.yaml` 옆에 있지만 플러그인 소유이며, `/flow-init` 실행마다 덮어써짐. 호스트
사본을 편집해도 다음 실행까지만 남고, 플러그인 캐시를 편집해도 다음 업데이트까지만 남음.
호스트에서 지속적으로 바꿀 방법은 없음 — 강제를 아예 끄려면
[`/flow-uninstall`](update-and-removal.ko.md#flow-uninstall--호스트-배선-제거) 을 실행.

두 가지를 담음: 등급별 필수 게이트, 그리고 `merge_strategy`(브랜치 흐름별 `git merge` 가
가져야 할 플래그). 둘 다 [등급과 게이트](tiers-and-gates.ko.md) 에서 다룸.
