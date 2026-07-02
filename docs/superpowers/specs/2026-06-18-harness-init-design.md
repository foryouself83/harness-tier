# `/harness-init` — 하네스 자동 구축 설계

> 상태: 설계(브레인스토밍 산출물). 다음 단계 = writing-plans 로 구현계획 작성.
> 작성일: 2026-06-18 · 브랜치: `feature/harness-init`

## 1. 목적

사용자에게 문맥을 받아, 대상 개발 프레임워크에 맞는 **AI 하네스**(Claude Code 컨텍스트
스캐폴딩)를 자동 생성한다. 프레임워크/버전을 자동 감지하고 **매회 웹검색**으로 최신
폴더/스키마 컨벤션·베스트프랙티스·보안 도구를 끌어와, 간결하고 보기 쉬운 하네스를
만든다.

레퍼런스(실재 확인): [`revfactory/harness`](https://github.com/revfactory/harness)
(메타-스킬, 에이전트팀+스킬 생성), [`aiming-lab/AutoHarness`](https://github.com/aiming-lab/AutoHarness).
**차별점**: (1) command/agent/skill/rule **4종 전부** 생성 + CLAUDE.md/docs, (2)
프레임워크 **특화** 최신 컨벤션을 웹검색으로 조달, (3) Karpathy CLAUDE.md 원칙 + 간단
보안을 **항상 주입**.

## 2. 확정 요구사항

| 항목 | 결정 |
|------|------|
| 산출물 | **하네스 관련 .md 파일만**이 기본: `CLAUDE.md`·`docs/`·`.claude/*`(agents·commands·skills·rules). 실설정(bandit·CI·pre-commit·실폴더 스캐폴딩·실제 버전핀)은 **항목별 consent로 opt-in** |
| 구현 여부 | **flow를 따라 구현하지 않음** — superpowers/게이트 사이클 안 돎. 순수 생성기 |
| 대상 감지 | init 시 그린/브라운 **자동 감지**. 브라운필드는 "있으면 스킵, 없으면 추가 or 사용자선택", **절대 덮어쓰기 X** |
| 최신성 | 매니페스트로 프레임워크·버전 **자동 감지** → 전용 research 에이전트가 **매회 웹검색**, 출처 URL 첨부 |
| 보안 | 보안 룰 기본 탑재(.md) + 프레임워크별 스캐너(bandit/npm audit/gosec)는 **물어보고 opt-in 설치** |
| 필수 주입 룰 | Karpathy CLAUDE.md 원칙 전체 + DRY/매직값상수화(별도) + `==` 버전고정(별도) + 보안 |
| UX | 간결·가독성 우선. 검증→계획→**미리보기**→확정→쓰기 |

## 3. 아키텍처 (접근 A — vway-kit 네이티브)

```text
commands/
  harness-init.md            얇은 대화형 오케스트레이터 (감지→인터뷰→리서치→생성→보고)
agents/
  harness-researcher.md      격리 컨텍스트 웹리서치 → 구조화 결과+출처 반환
skills/
  harness-authoring/
    SKILL.md                 생성 규율 + 진입점 (얇게)
    templates/               채워넣을 골격 (생성 시 참조)
      skill.template.md
      command.template.md
      agent.template.md
      rule.template.md
      claude-md.template.md
    references/
      authoring-spec.md      4종 frontmatter·구조 작성법 + 공식문서 SSOT 링크
      karpathy-principles.md  Karpathy claude.md 4원칙 distill (출처 명기)
      rule-dry-constants.md   매직값 상수화/DRY (Karpathy 내용이나 별도 명시)
      rule-version-pinning.md == 정확 버전 고정 (별도 룰)
      security-rule.md        시크릿·.env·입력검증
rules/
  harness-rules.md           하네스 생성 규율 SSOT (SessionStart 자동주입 X — /harness-init만 defer)
scripts/
  harness_scaffold.py        결정론·멱등: detect / plan / apply (pytest 대상)
tests/
  test_harness_scaffold.py
```

**4종 컴포넌트의 이중 역할**: 기능 자체가 command+agent+skill+rule로 구성(구조적
충족) + authoring 스킬이 4종 "작성법" 보유 → 호스트에 4종 모두 생성(기능적 충족).

**경로 규율(불변식)**: 읽기 `${CLAUDE_PLUGIN_ROOT}`(템플릿/references), 쓰기
`${CLAUDE_PROJECT_DIR}`(호스트). 플러그인 디렉터리엔 쓰지 않음.

**`rules/harness-rules.md`는 risk-tiers.md와 달리 SessionStart 주입 안 함** — 하네스
생성은 가끔 하는 작업이라 매 세션 주입은 컨텍스트만 오염. /harness-init 실행 시점에만
defer.

## 4. 엔드투엔드 플로우

```text
Step 0 — 검증/감지 (harness_scaffold.py detect)  → §6 인벤토리 전수
Step 1 — 인터뷰 (AskUserQuestion, 최소화)
          · 감지 프레임워크/버전 확인(틀리면 정정)
          · 생성 산출물 선택 (.md 기본) + 실설정 opt-in 여부(bandit·CI·폴더 등)
          · 브라운필드 충돌 항목별 스킵/사용자선택
Step 2 — 리서치 (harness-researcher 에이전트, 격리)
          입력: framework+version+관심사 → 출력(구조화+출처):
          최신 폴더/레이아웃 · 스키마/설정 컨벤션 · 베스트프랙티스 N · 보안스캐너+CI스니펫 · 취약/최소버전
Step 3 — 생성 (authoring 스킬 + scaffold)
          · 템플릿 복제 → research + karpathy/security 블록으로 채움(간결)
          · harness_scaffold.py plan → 미리보기(생성/스킵/충돌) → 확정 → apply (멱등, 덮어쓰기 X)
Step 4 — 보고
          생성/스킵/사용자보류 + 출처 URL + 후속(보안스캐너 설치 등) — 표로 간결
```

**데이터 흐름**: 사용자 → 명령 → 감지스크립트 → 인터뷰 → 리서치에이전트 → (명령이
템플릿+리서치로 생성계획 조립) → scaffold apply → 보고. **harness-init은 커밋하지
않는다** — 사용자가 별도로(필요시 `/flow`로) 커밋.

## 5. 생성물 & 안전성

**그린필드 기본 산출물(.md)**:

```text
CLAUDE.md                      개요 + 필수룰 3기둥(본문/명시 import) + 프레임워크 컨벤션 요약
.claude/rules/
  baseline.md                  Karpathy + DRY/상수 + ==버전핀 + 보안
  <framework>-conventions.md   research로 채운 최신 폴더/스키마/베스트프랙티스
.claude/skills|commands|agents/ 필요 시 템플릿 기반 생성
docs/                          가이드/표준 문서
```

**opt-in(동의 시에만 실제 적용)**: 프레임워크 실폴더 스캐폴딩, CI 보안 워크플로,
pre-commit 보안 훅(bandit/gosec 등), 매니페스트 실제 `==` 버전핀.

**브라운필드 안전**:

| 상황 | 동작 |
|------|------|
| 파일 없음 | 생성 |
| 파일 존재 | **덮어쓰기 X** → 기본 스킵+보고, 또는 사용자선택(diff 후 추가) |
| CLAUDE.md 일부 존재 | 마커블록(`<!-- harness:baseline BEGIN/END -->`)으로 누락 룰만 삽입, 사용자/flow-init 내용 보존 |
| 폴더 일부 존재 | 누락 디렉터리만 제안, 기존 코드 미이동 |

## 6. 사전 검증 (detection-first) — 전수 인벤토리

**철칙**: 어떤 파일도 쓰기 전 전부 검증 → 계획(생성/스킵/충돌/물어보기) → **미리보기**
→ 확정 → 쓰기. 모호하면 추측 말고 질문. 검증은 `harness_scaffold.py detect`(테스트됨).

| 분류 | 검증 항목 | 발견 시 동작 |
|------|----------|-------------|
| 프로젝트 상태 | 파일수·소스유무·VCS → green/brown | 스캐폴딩 제안 범위 결정 |
| 프레임워크 | package.json·pyproject·go.mod·Cargo·pom·Gemfile·composer / 모노레포 다중 | 미감지/모호 → **질문** |
| CLAUDE.md | 존재·내용(flow-init `vway-kit:teams`블록 / 수기룰 / 기존 Karpathy / 이전 `harness:baseline` 마커) | 마커 in-place, 사용자/flow 내용 불가침 |
| .claude/rules | 기존 룰·baseline.md | 누락분만, 로드경로 보장(§7-A) |
| .claude/skills·commands·agents | 기존 컴포넌트 **이름 + frontmatter `description`** | 동명 충돌 + **의미상 기능 중복** 확인 → 스킵/물어보기, 덮어쓰기 X, 예약명 회피 |
| docs/ | 기존 문서·인덱스 | 누락분만 |
| flow/vway-kit | flow-config.yaml · .claude/vway-kit/ · settings.json 훅 | 감지 시 **프로세스룰 risk-tiers defer** |
| 보안·CI | .pre-commit-config.yaml(+훅 id) · .github/workflows · .bandit/[tool.bandit]/.eslintrc | 기존 **자동병합 X**, 누락만 보고+opt-in |
| 버전핀 | 매니페스트 == 고정 여부 | 정보용(자동수정 X), 안내만 |
| 이전 실행 | `.claude/.harness/manifest.json` | 멱등 재실행 / 버전델타 최신화 |

> 컴포넌트 중복 검사는 **이름 + description 까지만** 읽는다(세부 본문 X). description
> 유사도로 "이미 비슷한 일 하는 컴포넌트"를 잡아 중복 생성을 막는다.

## 7. 필수 주입 룰 (Karpathy 기반)

생성되는 호스트 `CLAUDE.md`/`.claude/rules/baseline.md`의 **기반(SSOT)**. 구현 시
**실제 Karpathy CLAUDE.md를 웹리서치해 distill**(추측 금지). 원전: Forrest Chang가
Karpathy의 LLM 코딩 관찰을 distill한 `andrej-karpathy-skills`(Claude Code 스킬로
패키징; 포크 예 [swarmclawai](https://github.com/swarmclawai/andrej-karpathy-skills) ·
[multica-ai](https://github.com/multica-ai/andrej-karpathy-skills), 개요
[AI Builder Club](https://www.aibuilderclub.com/blog/karpathy-claude-md-rules)).
구현 시 정확 원전 URL을 확인해 실제 파일을 fetch한다.

Karpathy 4원칙:
1. **Think Before Coding** — 가정 명시, 모호하면 **추측 말고 질문**, 복수 해석 제시, 필요시 반박
2. **Simplicity First** — 최소 코드, 미요청 추상화/기능/설정 금지, 과방어 금지
3. **Surgical Changes** — 변경 줄이 요청에 직결, 건드릴 것만
4. **Goal-Driven Execution** — 검증가능 성공기준 + 체크포인트 계획

별도 명시 룰:
- **DRY / 매직값 상수화** (Karpathy 내용이나 독립 룰로 가시화)
- **`==` 정확 버전 고정** (`>=`/이상 금지 — 패키지/라이브러리/컨테이너)
- **간단 보안** — 시크릿/키 커밋 금지, .gitignore 보강, .env 취급, 입력검증 기본

## 8. `/flow` 비(非)모순 설계

harness-init = **생성기(.md + opt-in 설정)**, /flow = **변경 거버넌스(분류·게이트·커밋)**.
책임 분리로 모순을 구조적으로 제거. harness-init 산출물도 결국 /flow 게이트를 통과해 들어감.

| # | 충돌 | 해소책 |
|---|------|--------|
| A | 생성한 `.claude/rules/*`가 **자동 로드 안 됨**(vway-kit조차 훅 주입으로 risk-tiers 적용) | 필수 룰을 **CLAUDE.md 본문에 직접** 넣거나 CLAUDE.md에서 **명시 import**. "폴더에 두면 켜진다" 가정 금지 |
| B | 호스트에 **이미 CLAUDE.md 존재**(flow-init 블록/수기) | 마커블록으로 누락분만, flow-init·사용자 내용 불가침 |
| C | `/flow-init` vs `/harness-init` 혼동 | 역할 명시 + flow 감지 보고. 문서에 "언제 무엇" |
| D | 생성 CLAUDE.md가 risk-tiers와 프로세스 규칙 충돌(PR·머지·커밋) | flow 감지 시 프로세스 규율 **risk-tiers defer**, 하네스는 코드스타일+프레임워크 컨벤션만 |

## 9. 에러 처리 · 테스트 · 간결성

**에러 처리**: 웹리서치 실패 → "최신"을 지어내지 않음, 경고+「최소 일반구조로 진행/중단」
선택(정적 룰은 항상 생성 가능). 프레임워크 미감지 → 질문. 브라운필드 충돌 → 스킵/선택.
재실행 → 멱등. 스크립트 인코딩 → `PYTHONUTF8=1`·`encoding="utf-8"`.

**테스트**(`tests/test_harness_scaffold.py`): 그린필드 생성 / 브라운필드 스킵 / 충돌
보고 / **재실행 멱등**(파일 1회·마커 중복없음) / **덮어쓰기 금지 불변식** / 마커
in-place 교체 / description 기반 중복감지.

**간결성**: 생성 .md lean(authoring-spec이 강제), 인터뷰 최소 라운드+스마트 기본값,
보고는 표/출처, apply 전 미리보기.

## 10. 범위 밖 (YAGNI)

- harness-init 자체의 커밋/머지(= /flow 책임)
- 프레임워크 풀 부트스트랩(런타임 설치·DB 마이그레이션 등 — opt-in 스캐폴딩까지만)
- 비-Claude 에이전트(AGENTS.md/Cursor 등) 멀티타깃 출력 — 후속

## 11. 미해결/후속

- `.claude/.harness/manifest.json` 기반 "버전 상승 → 변경분만 최신화" 모드(후속)
- 생성 docs를 flow-config.doc_sync 인덱스에 자동 등록(통합 enhancement)
