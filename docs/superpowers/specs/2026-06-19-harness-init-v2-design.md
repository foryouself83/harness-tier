# `/harness-init` v2 — 다중 에이전트(서브에이전트 fan-out) 생성·비판 파이프라인 설계

> 상태: 설계(브레인스토밍 산출물). 다음 단계 = writing-plans 로 구현계획 작성.
> 작성일: 2026-06-19 · 기반: [v1 설계](2026-06-18-harness-init-design.md)
> 레퍼런스(전수 정독): [`revfactory/harness`](https://github.com/revfactory/harness) — SKILL.md + 6 references

## 1. 배경 / 문제

v1 harness-init 파이프라인은 `detect → interview → research(단일 에이전트) → author(템플릿) →
preview → apply → report` 다. 동작하지만 **생성물 품질 보증이 얇다**:

1. **사유(rationale) 부재** — 리서치와 생성 사이에 "왜 이 컴포넌트를 이렇게 만드는가"의
   문서화가 없다. revfactory의 Domain Analysis + 결정 로깅에 해당하는 단계가 비어 있다.
2. **비판/검증 부재** — 생성 후·확정 전에 산출물을 검토하는 단계가 없다. revfactory Phase 6
   (구조검증·정합성·드라이런)에 해당하는 게 없다.
3. **산출물 완전성 부족** — 템플릿이 최소 골격이라 placeholder만 채운다. 기술문서(아키텍처·
   코드스타일·온보딩)가 없고, 작성 품질 규율(pushy description·Why-first·progressive
   disclosure)이 강제되지 않는다.
4. **단일 에이전트의 한계** — 웹 컨벤션만 보는 단일 리서처는 "프로젝트가 이미 손수 구현한 것"과
   "기성 솔루션으로 대체 가능한 것"을 교차 판단하지 못한다.

v2는 이 4개 공백을 메운다. **후속 진화(revfactory Phase 7)는 도입하지 않는다** — 원샷 생성기다.

## 2. 목표 / 비목표

**목표**
- 첫 생성 시점에 **완전하고 고품질인 하네스 산출물**을 만든다: CLAUDE.md baseline + 룰(코드스타일·
  컨벤션) + skills + agents + 기술문서 3종.
- 품질을 **사유 작성 → 다중 에이전트 리서치(팀) → 작성 → 경량 비판/검증 → 미리보기 → 확정**으로 보증.
- **재사용·기성 우선(reuse-before-build)** 원칙을 리서치·비판·생성물 전반에 주입.

**비목표 (YAGNI)**
- 후속/유지보수 모드(부분 재실행, drift 감사, 변경이력 진화). manifest 기록은 감사용으로만 유지.
- 풀 eval 하네스(with/without-skill 실행비교·assertion 채점·iteration workspace).
- 슬래시 커맨드 생성 (§3 결정 D).
- harness-init 자체의 커밋/머지/PR (= /flow 책임).

## 3. 핵심 설계 결정

| # | 결정 | 근거 |
|---|------|------|
| A | **런타임 = `Agent`(구 `Task`, alias) 서브에이전트 병렬 fan-out**(표준, 모든 빌드). 교차대화는 Agent Teams 실험 기능(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)이 켜진 경우만 `SendMessage` 옵션. 폐기 도구(TeamCreate/TaskCreate) 미사용 | 표준 fan-out 은 어디서나 동작, 교차대화는 켜진 빌드에서 reuse-before-build 정확도를 더함 |
| B | **검증 = 경량 2층**: `harness_scaffold.py validate`(결정적 구조) + `harness-critic` 에이전트(품질·정합성) | 원샷 생성기엔 풀 eval 과도 |
| C | **사유 작성** 단계 신설 → `.harness/rationale.md` | revfactory Domain Analysis + 결정 로깅 차용 |
| D | **커맨드 미생성** (v1의 "4종 전부" 결정을 뒤집음) | 사용자 요구 + revfactory도 커맨드 비생성·검증 |
| E | **reuse-before-build를 5번째 필수 baseline 룰로 주입** (레지스트리 탐색, **무료·상용가능만 추천·유료 제외**) | 생성된 하네스가 추후 구현도 무료 기성 우선으로 유도 |
| F | **기술문서 3종 생성**: ARCHITECTURE.md · code-style.md(BP+안티패턴) · onboarding.md | 사용자 지정 |

## 4. 엔드투엔드 파이프라인 (v1 → v2)

```text
v1: detect → interview → research(1 agent) → author → preview → apply → report
v2: detect → interview → research(서브에이전트 fan-out) → 사유작성 → author → 비판/검증(루프) → preview → apply → report
```

| Step | 내용 | 변경 |
|------|------|------|
| 0 감지 | `harness_scaffold.py detect` (상태/프레임워크/기존 컴포넌트) | 유지 |
| 1 인터뷰 | 산출물 선택: CLAUDE.md / 룰(baseline 5종 + 프레임워크 컨벤션) / skills / agents / 기술문서 3종(ARCHITECTURE·code-style·onboarding). **command 선택지 제거.** 실설정 opt-in 유지 | 보강 |
| 2 리서치 | **서브에이전트 fan-out** — `harness-researcher`(웹 컨벤션+BP+안티패턴 + **레지스트리 기반 기성솔루션 탐색**: 후보별 비용·라이선스·유지보수 확인, 무료·상용가능만 추천·유료 제외) + 브라운필드 시 `harness-code-analyzer`(코드베이스 실제 스타일·반복패턴·안티패턴·손수구현 발견). 병렬 `Agent` 디스패치·팬인, 교차대화는 실험 기능 켜진 경우 `SendMessage` 옵션. 산출 → `.harness/research/*.md` | **신규** |
| 3 사유 작성 | 리더가 detect+research 종합 → `.harness/rationale.md`: 도메인 분석, **산출물별 생성 사유**, 채택 패턴, BP/안티패턴 요약, **reuse-before-build 권고**, 출처 | **신규** |
| 4 생성 | 강화된 `harness-authoring`(작성 품질 references) + 기술문서 템플릿 → `.harness/plan.json` | 보강 |
| 5 비판/검증 | (a) `validate`(결정적) → (b) `harness-critic`(품질·정합성·reuse 위반·커맨드 미생성) → 이슈 시 author 재작성 **최대 2회** → 잔여는 "미해결" 명시 | **신규** |
| 6 미리보기 | plan + rationale + critic 리포트 함께 제시 → 확정 | 보강 |
| 7 apply | `harness_scaffold.py apply` (마커 upsert/create, 덮어쓰기 금지) | 유지 |
| 8 보고 | `manifest.json`(생성내역+프레임워크+출처+critic 결과) + 후속 안내. **커밋 안 함** | 보강 |

## 5. 멀티에이전트 오케스트레이션

**리더** = `harness-init` 스킬 본문(메인 루프). 스크립트 실행·authoring·apply 담당.

### 5-1. 리서치 fan-out (Phase 2) — 병렬 디스패치/팬인 (+옵션 교차대화)
```text
Agent(harness-researcher)        # 웹 컨벤션·BP·안티패턴·무료 기성솔루션
Agent(harness-code-analyzer)     # 브라운필드일 때만, 코드베이스 컨벤션·안티패턴
  → 두 서브에이전트를 병렬 디스패치
교차대화(옵션 — CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 켜진 빌드에서만 SendMessage):
  code-analyzer → researcher : "프로젝트가 X를 손수 구현함 — 대체 기성 솔루션 조사 요청"
  researcher → code-analyzer : "BP가 Y를 권장 — 코드가 위반하는지 확인 요청"
팬인: 리더가 .harness/research/*.md 를 Read 로 수집
```
> 폐기된 `TeamCreate`/`TaskCreate`/`TeamDelete`(v2.1.178+ 제거)는 쓰지 않는다.

### 5-2. 비판 루프 (Phase 5) — 생성-검증 (경량, FAIL-OPEN)
```text
author → validate (스크립트, 결정적)
       → harness-critic (general-purpose, model: opus) 리뷰
       → 이슈 있으면 리더가 author 수정 (최대 2회)
       → 잔여 이슈는 미리보기/보고에 "미해결"로 명시
       → 최종 판단은 사용자가 미리보기에서
```
> critic 은 단일 `Agent` 서브에이전트. 리더↔critic 반복은 반환값 기반(교차대화 불필요).

### 5-3. 표준 vs 교차대화
**표준 = `Agent`(구 `Task`, alias) 서브에이전트 병렬 디스패치**(모든 빌드 동작, 교차대화 없이 팬인으로 종합).
Agent Teams 실험 기능이 켜진 빌드에서만 `SendMessage` 교차대화를 **옵션**으로 더한다. 산출물은 동일,
교차대화 여부만 다르다.

### 5-4. 데이터 전달 (파일 기반)
모든 중간 산출물은 `.harness/` 아래 파일로 — revfactory `_workspace/` 패턴을 vway-kit 규약에 맞춤.
```text
.claude/vway-kit/.harness/
  research/<agent>_<topic>.md     리서치 팀 산출 (격리)
  rationale.md                    사유
  plan.json                       생성 계획 (apply 입력)
  critic-report.json              비판 결과
  manifest.json                   최종 감사 기록
```
`.harness/` 는 첫 쓰기 전 `.gitignore` 멱등 추가(harness-init 독립, flow-init 의존 금지).

## 6. 산출물

### 6-1. 호스트 생성물 (`${CLAUDE_PROJECT_DIR}`)
```text
CLAUDE.md                         개요 + harness:baseline 마커블록(필수룰 5종) + 프레임워크 컨벤션 요약
.claude/rules/
  baseline.md                     필수 5종 (CLAUDE.md 본문 주입과 병행 — 로드경로 보장)
  <framework>-conventions.md      **구조적** 컨벤션: 폴더/레이아웃·스키마/설정 ("어디에 두는가")
.claude/skills/<name>/SKILL.md     필요 시 (작성 품질 강제)
.claude/agents/<name>.md           필요 시 (정의 구조 강제)
docs/
  ARCHITECTURE.md                 프레임워크·폴더구조·주요모듈 (브라운필드면 스캔값)
  code-style.md                   **행위적** 가이드: 네이밍·포맷·임포트 + BP + 안티패턴 + reuse 예시 ("어떻게 쓰는가")
  onboarding.md                   실행·브랜치·디버그 개요 (greenfield 유용)
```
**커맨드는 생성하지 않는다.**

> **SSOT 분리(생성물 중복 방지)**: 같은 컨벤션을 룰과 문서에 중복하지 않는다. *구조적 레이아웃*은
> `<framework>-conventions.md`(룰), *작성 스타일·BP·안티패턴*은 `docs/code-style.md`(문서)에만 둔다.
> reuse-before-build는 *원칙*은 baseline 룰(§7), *프레임워크별 구체 예시*는 code-style 문서.
> 룰이 문서를 가리키되 내용을 복제하지 않는다(critic이 중복을 검사).

### 6-2. 증거 (`.claude/vway-kit/.harness/`, gitignored)
§5-4 목록. 감사·재실행 판단용. 커밋되지 않음.

## 7. 필수 baseline 룰 (4 → 5종)

기존 4종(Karpathy 4원칙 · DRY/상수 · `==`버전핀 · 보안)에 **reuse-before-build** 추가:

> **rule-reuse-first.md** — 직접 코드 구현 전에, **무료이면서 상용 사용이 허용되는** 기성 솔루션을
> 먼저 **탐색·추천**한다. 탐색 범위(도구 기반): 공식 Docker 이미지, 표준 라이브러리, 프레임워크
> 빌트인, 패키지 레지스트리(Docker Hub·PyPI·npm 등)의 잘 유지되는 OSS.
> **비용·라이선스 게이트**: 후보마다 비용(무료?)·라이선스(상용 가능?)·유지보수 상태를 확인하고,
> **유료 솔루션(유료 매니지드 서비스·상용 라이선스·SaaS 구독)은 추천하지 않는다.**
> 무료·상용가능 후보가 없거나 요구사항에 부적합하면 직접 구현한다.
> **Why**: 직접 구현은 유지보수·보안·엣지케이스 부담을 새로 떠안는다. 무료 OSS 기성품은 그 부담을
> 외부화하면서 비용·라이선스 제약도 없다.

5종 모두 CLAUDE.md `harness:baseline` 마커블록에 주입(로드경로 보장 — `.claude/rules/` 단독 배치 금지).
reuse-first는 추가로 **code-style.md 안티패턴 섹션**("바퀴 재발명")과 **researcher/code-analyzer/critic
규율**에도 반영된다.

## 8. 신규/수정 컴포넌트 (파일 단위)

**플러그인 (SOURCE·SSOT)**
| 파일 | 작업 | 내용 |
|------|------|------|
| `agents/harness-code-analyzer.md` | **신규** | Explore 타입. 코드베이스 실제 컨벤션·반복패턴·안티패턴·손수구현 추출, 출처(파일:라인). 팀 통신 프로토콜 포함 |
| `agents/harness-critic.md` | **신규** | general-purpose. 생성물 품질(작성가이드)·경계면 정합성·reuse 위반·커맨드 미생성 검토. 구조화 리포트 출력 |
| `agents/harness-researcher.md` | 수정 | BP/안티패턴 + 기성솔루션(이미지·서비스·라이브러리) 항목 추가, 팀 통신 프로토콜 추가 |
| `skills/harness-authoring/references/skill-writing-guide.md` | **신규** | pushy description·Why-first·progressive disclosure·일반화·예시·번들링 (revfactory 차용·압축) |
| `skills/harness-authoring/references/agent-design-guide.md` | **신규** | 분리기준·중복검토·정의구조 (차용·압축) |
| `skills/harness-authoring/references/critique-guide.md` | **신규** | 구조검증·경계면 정합성·드라이런 체크리스트 (critic가 defer) |
| `skills/harness-authoring/references/tech-doc-guide.md` | **신규** | ARCHITECTURE/code-style(BP·안티패턴)/onboarding 작성법 |
| `skills/harness-authoring/references/rule-reuse-first.md` | **신규** | §7 reuse-before-build 룰 본문 |
| `skills/harness-authoring/templates/architecture.template.md` | **신규** | 기술문서 골격 |
| `skills/harness-authoring/templates/code-style.template.md` | **신규** | BP·안티패턴 섹션 포함 골격 |
| `skills/harness-authoring/templates/onboarding.template.md` | **신규** | 온보딩 골격 |
| `skills/harness-authoring/templates/command.template.md` | **삭제** | 커맨드 미생성 |
| `skills/harness-authoring/templates/{skill,agent,rule}.template.md` | 수정 | 작성가이드 반영(pushy description·Why-first 골격) |
| `skills/harness-authoring/SKILL.md` | 수정 | 신규 references/templates, 3종(skill/agent/rule)+기술문서, 품질 규율 |
| `scripts/harness_scaffold.py` | 수정 | **`validate` 서브커맨드** 추가(frontmatter·룰 로드경로·dedup·dead-link·마커정합·커맨드 미생성) |
| `tests/test_harness_scaffold.py` | 수정 | validate 테스트 추가 |
| `rules/harness-rules.md` | 수정 | 사유·critic·기술문서·다중에이전트(팀)·reuse-first·커맨드 미생성 규율 |
| `skills/harness-init/SKILL.md` | 수정 | 신규 파이프라인·팀 오케스트레이션·폴백 |
| `README.md` · `USAGE.md` | 수정 | harness 섹션 갱신(doc-sync) |

## 9. `harness_scaffold.py validate` 명세

```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" validate --root "${ROOT}" --plan "${HARNESS_DIR}/plan.json"
```
결정적 구조검사(JSON 리포트 출력). **게이트가 아니라 진단** — 실패가 생성을 영구 차단하지 않음(FAIL-OPEN).

| 검사 | 규칙 |
|------|------|
| frontmatter | 생성 skill/agent에 `name`·`description` 존재·비어있지 않음 |
| 룰 로드경로 | 필수 5종이 CLAUDE.md `harness:baseline` 마커블록 안에 존재(`.claude/rules/` 단독 배치 금지) |
| dedup | 생성 컴포넌트 name이 기존(detect.existing)과 충돌하지 않음 |
| dead-link | 생성 .md 내부 상대링크가 plan/기존 파일을 가리킴 |
| 마커정합 | 마커블록 BEGIN/END 짝 정합(corrupt 차단) |
| **커맨드 미생성** | plan.files 에 `.claude/commands/` 경로 없음 |

Windows 인코딩 방어(`force_utf8_io`·`encoding="utf-8"`) 필수. 의존성(PyYAML) 부재는 폴백 라인파싱.

## 10. `harness-critic` 입출력 스키마

**입력**: plan.json + 생성 파일 내용 + 작성가이드(references) + 필수룰.
**출력** (구조화):
```json
{
  "issues": [
    {"severity": "high|med|low", "file": "<rel>", "kind": "quality|coherence|reuse|command",
     "evidence": "<근거>", "fix": "<수정 제안>"}
  ],
  "summary": {"high": 0, "med": 0, "low": 0, "verdict": "pass|revise"}
}
```
검토 영역: ① 작성 품질(description 적극성·Why-first·lean·일반화·로드경로) ② 경계면 정합성(CLAUDE.md↔룰
로드, 산출물 상호참조, dead-link) ③ **reuse 위반**(생성 가이드가 무료 기성 솔루션 대신 바퀴 재발명을
권하는가, **또는 유료 솔루션을 추천하는가**) ④ 커맨드 미생성 재확인. `verdict: revise` 면 리더가 최대 2회 재작성.

## 11. revfactory 차용 / 차이 / 불변

| 구분 | 항목 |
|------|------|
| **차용** | 작성품질(pushy desc·Why-first·progressive disclosure·일반화·예시·번들링) · 에이전트 설계(분리기준·중복검토·정의구조) · QA(경계면 정합성·드라이런·구조검증) · 팬아웃/팬인·생성-검증 패턴 · 파일기반 전달 · 사유(도메인 분석) |
| **차이** | 커맨드 생성(✗ v2도 비생성으로 정렬) · Phase 7 진화(✗) · 풀 eval(✗→경량) · CLAUDE.md는 baseline 룰 마커(우리 목적) |
| **불변** | preview→confirm→write · 덮어쓰기 금지 · dual-path(PLUGIN읽기/PROJECT_DIR쓰기) · flow 감지 시 risk-tiers defer · Windows 인코딩 · 멱등 · 커밋 안 함 |

## 12. 테스트 계획

`tests/test_harness_scaffold.py` 확장:
- validate: frontmatter 누락 탐지 / 룰 로드경로 위반 탐지 / dedup 충돌 탐지 / dead-link 탐지 / 마커 corrupt 탐지 / **커맨드 경로 포함 시 탐지**.
- 기존 detect/apply/멱등/덮어쓰기금지 테스트 유지.
- 에이전트·스킬·문서 산출물은 .md 텍스트라 단위테스트 대상 아님 — critic/사용자 미리보기가 검증.

## 13. 리스크 / 오픈이슈

- **교차대화 가용성**: `SendMessage`(Agent Teams)는 실험 기능이 켜진 빌드에만 존재 → 표준은 `Agent`(구 `Task`) 서브에이전트 fan-out, 교차대화는 §5-3 옵션. 폐기된 `TeamCreate`/`TaskCreate` 의존 금지.
- **critic 무한루프 방지**: 재작성 최대 2회 하드캡, 잔여는 "미해결" 명시(차단 X).
- **기술문서 위치**: repo `docs/` 관례가 다를 수 있음(예: `documentation/`) → 인터뷰에서 확인 또는 기존 docs 디렉터리 감지.
- **reuse-first 과적용**: 정당한 커스텀 구현까지 막지 않도록 룰에 "무료·상용가능 기성이 없거나 부적합하면 구현" 예외 명시.
- **라이선스·비용 판정 정확도**: researcher가 후보의 라이선스/유료 여부를 레지스트리·공식문서에서 확인하되, 불확실하면 "확인 필요"로 표기하고 단정하지 않는다(지어내기 금지). critic이 유료 추천을 2차 검사.
