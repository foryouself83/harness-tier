# 등급과 게이트

[English](tiers-and-gates.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

작업은 네 등급 중 하나로 분류되고, 그 등급이 커밋 전에 통과해야 할 게이트를 정함. 분류
규칙 자체는 [`rules/risk-tiers.md`](../../rules/risk-tiers.md) 에 있고, SessionStart 훅이
모든 세션에 주입함.

## 등급

| 등급 | 시점 | superpowers | 필수 게이트 |
|------|------|:---:|--------------|
| `docs` | 코드 없는 변경(문서, 주석, 설정값) | ✗ | `doc-sync` · `wiki` · `doc-style` |
| `dev` | 코드가 있는 변경(기능, 수정) | ✓ | `precommit` · `review` · `doc-sync` · `wiki` · `doc-style` |
| `staging` | integration → staging 승격 | ✗ | `precommit` · `review` · `security-scan` · `bump` · `wiki` · `doc-style` |
| `release` | staging → production 승격 | ✗ | `precommit` · `security-scan` · `security` · `wiki` · `doc-style` |

`docs`·`dev` 는 [`/flow`](daily-work.ko.md#flow--일상-작업-라우터) 가 정해 `tier` 마커를 씀.
`staging`·`release` 는 커밋이 놓이는 브랜치가 정하고 [`/release-commit`](promotion-and-release.ko.md)
이 실행함. Release 에는 `review` 가 없음 — Dev 와 Staging 에서 이미 그 diff 를 읽었기 때문.

## 게이트가 보는 것

작업을 검사하는 층은 셋이고, 각각 다른 커밋 집합을 봄:

1. **pre-commit** — `.pre-commit-config.yaml`: `pre-commit install` 이 실행된 저장소의
   모든 `git commit` 에서 커밋 메시지 검사와 파일 점검을 함.
2. **flow 게이트** — `/flow-init` 이 `.claude/settings.json` 에 등록하는 `PreToolUse` 훅. **Claude
   세션에서 실행한** `git commit`·`git merge` 명령만 봄. 터미널·CI·GitHub 상의 커밋이나 머지는
   이 층을 건너뜀.
3. **CI** — `/flow-init` 이 렌더링하는 워크플로들, 모든 push 에서 돌아 2층이 남기는 공백을
   메움([CI 워크플로](ci-workflows.ko.md)).

이 페이지의 모든 게이트는 2층에 속함. 훅 항목은 600초 timeout 을 가지며 그 안에서 실행하는
모듈 검사 전부를 덮음; 검사 하나에는 별도 timeout 이 없음.

## 게이트

### 증거 게이트 — `review` · `doc-sync` · `security` · `bump`

각각 마커 `.claude/harness-tier/.flow/<gate>.done` 이 있으면 통과함. 게이트를 실행한 스킬이
마커를 씀 — `/flow` 는 `review`·`doc-sync`, `/release-commit` 은 승격 시 `review`·`bump`·
`security`. `bump` 는 사람이 고르는 major/minor/patch 선택이고 fail-closed — 선택할 때까지
staging 커밋이 막힘.

### 모듈 검사 게이트 — `precommit` · `security-scan`

커밋 훅이 `modules[].checks` 를 직접 실행함: `precommit` 은 변경된 모듈의 `every-commit`
검사, `security-scan` 은 모든 모듈의 `promotion` 검사
([`when`](configuration.ko.md#modules-와-checks)). 명령이 0 이 아닌 코드로 끝나면 커밋이
차단됨. 출력은 버퍼링되어 실패할 때만 출력됨. 등급 정책의 게이트 목록에서 둘 중 하나를
빼면 그 등급에서 그 검사 묶음이 꺼짐.

### `wiki`

`flow-config.wiki.enable` 이 켜져 있을 때만 훅 프로세스 안에서 실행되고, 아니면 아무것도
하지 않음. `docs/graph/graph.yaml` 을 문서의 front matter 와 대조하며 읽기 전용이고,
**작업 트리**를 읽음 — 훅은 `git commit` 이 스테이징하기 전에 실행되기 때문. `graph.yaml`
을 만든 문서들과 함께 스테이징해야 함; 재빌드했지만 스테이징하지 않은 그래프는 게이트를
통과시키면서 커밋에는 낡은 그래프가 실림.

두 가지를 차단함:

- 구조 위반 — 목록은 10개 항목과 개수로 제한;
- 노드의 `sources` 스탬프만 바뀌고 본문 편집이 없는 커밋. 두 가지 스탬프 교체는
  허용됨: `/doc-sync` 가 레거시 마커를 마이그레이션하는 경우, 그리고 바로 앞 커밋에 본문
  편집이 실린 스탬프(그 커밋의 이름 변경도 따라감).

그래프 품질 관련 발견은 통과한 커밋에서도 경고로 나옴: 고아 문서, 과대 문서, 디스크에
없는 `sources` 경로, `sources` 값이 없는 `sds` 문서, 규칙으로 승격할 만한 태그, 파싱에
실패한 front matter, `wiki_id` 없이 존재하는 위키 전용 필드.

### `doc-style`

절대 차단하지 않는 유일한 게이트. `flow-config.doc_style.enable` 이 켜져 있으면 `paths` 와
`exclude` 가 정한 범위 안에서 커밋이 바꾼 파일을 린트하고 **error** 등급 발견만 보고함 —
히스토리 서술, 계획 문서 포인터, 필러, 한국어 `~다` 종결 등
[`rules/doc-style.md`](../../rules/doc-style.md) 의 금지 목록. `LONG`·`CLAIM` 경고는
`doc_style_check.py --lint` 와 CI 에서만 보임.

최종 판정은 전체 트리를 보는 `doc-style.yml` 워크플로가 가짐. 훅과 CI 는 같은 함수로 범위를
읽으므로 `exclude` 는 양쪽에 함께 적용됨. `flow-config.yaml` 이 파싱되지 않으면 "꺼짐"이
아니라 CI 잡이 실패함. `enable: false` 면 어느 층에도 검사가 없음.

### SRS 무결성은 게이트가 아님

flow 게이트는 SRS 를 전혀 읽지 않음. `docs/srs/` 가 생기면 `/flow-init` 이 제안하는
`srs-verify.yml` 만이 죽은 요구사항 앵커나 두 브랜치가 각자 가져간 중복 번호를 잡아냄
([CI 워크플로](ci-workflows.ko.md)).

## 게이트 증거

`review`·`doc-sync` 는 작업 트리를 판단하므로, Claude 가 파일을 편집하면 `PostToolUse` 훅이
**둘 다** 지우고 — 리뷰가 요청한 수정도 포함 — 어느 증거가 무효화됐는지 세션에 알림. 그래서
수정은 `/doc-sync` 와 리뷰를 다시 거침. 훅이 보지 못하는 편집(터미널 명령, 다른 도구)은
마커를 그대로 남기니 직접 지워야 함.

`gate_evidence.invalidate_on_edit: false` 는 이 삭제를 끄되, 마지막 편집을 보지 못한 리뷰
아래 커밋되는 대가를 치름.

`tier` 마커는 브랜치에 묶임. `<gate>.done` 파일은 그렇지 않음 — `/flow` 와 `/release-commit`
은 끝날 때 증거를 지우지만, 그 단계 전에 멈춘 작업은 어느 브랜치에서든 다음 실행이 읽을
마커를 남김.

## 머지 전략

`flow-tiers.yaml` 의 `merge_strategy` 는 `git merge` 의 플래그를 그 브랜치 흐름과 대조함.
브랜치명은 `flow-config.branches` 에서 옴.

| 머지 | 강제 |
|------|------|
| `feature/*` → integration | `--squash` 필수 |
| `hotfix/*` → production | `--squash` 필수 |
| integration → staging | `--no-ff` 필수 |
| staging → production | `--no-ff` 필수 |
| `fix/*` → integration | `--no-ff` 금지 |

위반은 차단됨. 정답 플래그가 하나뿐인 흐름만 검사함: production → integration 백머지와
재승격 전 staging → integration 백머지는 fast-forward 나 `--no-ff` 둘 다 허용하고,
production → staging 백머지는 fast-forward 가 거부됐을 때 건너뛰길 원하는데 이는 어떤
`require` 규칙으로도 표현되지 않음. rebase 없이
올라온 `feature/*` 머지는 경고만 하고 차단하지 않음 — `origin` 참조가 오래됐을 때 오탐을
막기 위함.

게이트가 판단할 수 없는 명령은 통과시킴: 매칭되는 규칙이 없거나, 파싱할 수 없거나, 머지가
모두 다른 디렉터리에서 실행되는 경우. `cd` 뒤의 머지가 디렉터리를 명시하지 않는 머지 옆에
있으면 그래도 판단함.

이 검사는 직접 머지만 봄. PR 로 보낸 흐름은 GitHub 브랜치 룰셋으로 강제가 옮겨감 —
[PR 워크플로와 브랜치 룰셋](promotion-and-release.ko.md#pr-워크플로와-브랜치-룰셋). 모든 흐름의
절차는 [`rules/merge-strategy.md`](../../rules/merge-strategy.md) 참고.
