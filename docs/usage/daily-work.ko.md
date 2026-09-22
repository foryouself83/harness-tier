# 일상 작업

[English](daily-work.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

모든 작업은 `/flow` 로 시작하고, 그 작업이 만드는 모든 커밋은 `/commit` 을 거침. `/doc-sync` 와
`/prose-review` 는 `/flow` 가 실행하는 문서 게이트이며, 따로 부를 수도 있음.

## `/flow` — 일상 작업 라우터

```text
/flow <자유 텍스트 요청>
```

커밋으로 끝나는 모든 작업 — 코드든 문서든 — 의 첫 단계.

1. **분류** — 무엇을 바꾸는지로 Docs 또는 Dev 를 정함: 문서·주석·설정값만이면 Docs; 소스
   파일·의존성·스키마가 하나라도 있으면 Dev
   ([`rules/risk-tiers.md`](../../rules/risk-tiers.md) 에 전체 기준이 있음).
2. **등급 확인** — 사용자에게 확인받고 필요하면 재정의; 애매하면 상위 등급을 제안함.
3. **작업 브랜치로 이동** — 이미 `feature/*`·`fix/*`·`hotfix/*` 면 그대로 있음. integration·
   staging·production 브랜치 위에 있으면 `feature/<slug>` 또는 `fix/<slug>` 를 제안하고
   확인받음 — 트리가 깨끗하면 새로 받은 `origin/<integration>` 에서, 아니면 커밋되지 않은
   변경을 실은 현재 `HEAD` 에서 분기함.
4. **그 브랜치에 `tier` 마커를 씀.**
5. **등급별 절차 실행**:
   - **Docs** — 편집 → `/doc-sync` → `/commit`.
   - **Dev** — `superpowers` 파이프라인(설계 → 계획 → 구현 → 검증) → `/doc-sync` →
     `review_checklist` 와 변경된 모든 public 심볼의 호출자를 기준으로 한 도메인 리뷰 →
     `/commit`. 리뷰는 편집이 그것을 무효화하므로 마지막에 돌림.
6. **머지** — 브랜치 흐름의 [머지 전략](tiers-and-gates.ko.md#머지-전략)대로, 또는
   `merge_workflow.pull_request` 에 `daily` 가 있으면 PR 을 엶.
7. **증거 정리** — 머지 뒤, 또는 PR 이 머지된 뒤.

Dev 는 `superpowers` 플러그인이 필요함; 없으면 `/flow` 가 멈추고 설치법을 안내함. `/flow` 를
건너뛴 커밋은 [미분류](troubleshooting.ko.md#미분류-커밋으로-막혀요)로 남음.

승격 — integration → staging, staging → production — 은 `/flow` 작업이 아님. 대상 브랜치가
등급을 정하고 [`/release-commit`](promotion-and-release.ko.md) 이 실행함.

## `/commit` — 커밋 하나를 작성·발행

```text
/commit [tier · bump level · what changed]
```

`/flow` 와 `/release-commit` 이 각자의 커밋 단계에서 호출함. 파일 이름으로 대상을 스테이징하고,
Conventional Commits 타입을 고르고, 50/72 규칙을 확인한 뒤 `git commit` 을 실행함.
소비자 대상 `.md` 변경은 `feat` 또는 `fix` 로 분류함 — `docs`·`chore` 는 릴리스를 만들지
않기 때문.

- 존재하면 `commit_guide` 를 읽어([설정](configuration.ko.md#commit_guide)) 그 프로젝트
  사실을 우선함.
- 승격 커밋은 [`/release-commit`](promotion-and-release.ko.md#release-commit--승격-하나를-실행)
  이 설명하는 경우에만 `Release-Level:` 트레일러를 붙임.
- `--no-verify` 를 절대 쓰지 않고, `git add -A` 를 절대 쓰지 않으며, 메시지에 CI-skip 마커를
  절대 적지 않음 — GitHub 는 head 커밋 어디에서든 그것을 읽으면 워크플로 실행을 만들지 않음.

**분류하지 않음.** `/flow` 없이 `/commit` 만으로 낸 커밋도 여전히 미분류 상태이고 차단됨.

## `/doc-sync` — 문서를 맞춰 둠

```text
/doc-sync [preview | what changed and why]
```

`git diff` 로 변경을 읽어 문서를 따라오게 함:

- **코드 → 문서** — 바뀐 클래스·필드·라우트·함수를 다루는 문서를 갱신.
- **문서 → 문서** — `flow-config.doc_sync` 대상 전체에서 상호 참조·사실·색인 항목을
  점검하고, `README.ko.md` 같은 번역 쌍둥이에도 같은 변경을 적용. 출처가 서로 어긋나면
  코드가 config 를, config 가 색인을, 색인이 모듈별 문서를 이김.
- **위키** — `flow-config.wiki` 가 켜져 있으면 오래된 `sources` 스탬프를 갱신하고
  `docs/graph/graph.yaml` 을 재빌드.
- **모듈 `CLAUDE.md`** — 프로젝트에 하네스가 있으면(`docs/code-style/` 또는 형제 모듈의
  `CLAUDE.md`) `service_docs` 아래 없는 모듈에 새로 생성; 없으면 보고만 함. 기존 파일은
  빠진 부분만 채움.

재작성 뒤 손댄 파일에 `/prose-review` 를 돌리고, 통과하면 호출자가 누구든 `doc-sync` 증거
마커를 씀.

포크된 컨텍스트에서 실행되어 대화를 보지 못함 — 인자가 유일한 의도 전달 통로. 인자가
정확히 `preview` 면 아무것도 바꾸지 않고 계획만 하며 마커도 쓰지 않음; 그 단어를 포함할
뿐인 문장은 동기화 요청으로 처리됨.

## `/prose-review` — 문체 규칙 점검

```text
/prose-review [paths… | empty = the changed files]
```

주석·docstring·문서를 [`rules/doc-style.md`](../../rules/doc-style.md) 와 대조하고
재작성을 제안함.

- **패턴 절반** — 경로에 대해 `doc_style_check.py --lint`. 스크립트 없는 저장소는 이 절반만
  건너뛰고 나머지는 그대로 함.
- **판단 절반** — 주석·docstring·문단마다: *어떻게* 를 설명하는지, 코드가 대신 예외를 낼 수
  있는지, 자명한지, 숫자가 측정값인지 그냥 쓴 것인지.
- **증명** — 같은 경로에 `doc_style_check.py --verify-git`: Markdown 재작성은 모든
  heading·펜스 블록·URL·인라인 코드를 유지해야 하고, `.py`·`.sh` 는 주석·docstring 을
  제외한 코드가 바이트 단위로 같아야 함. 손실은 배포되지 않고 보고됨.

발견 내용은 작성 중인 언어로 돌아옴. 세 박스 키 `CRITICAL TRAP:`·`Trigger:`·`Symptom:` 는
검사기가 파싱하므로 그대로 씀.
