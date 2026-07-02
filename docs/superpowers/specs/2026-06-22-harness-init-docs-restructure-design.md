# harness-init 산출물 구조·검증·정리 개편 — 설계

> 작성일 2026-06-22 · 대상 `/harness-init` 및 그 호출 체인
> (`harness-authoring` 스킬 · `harness_scaffold.py` · `harness-critic`/`harness-researcher` 에이전트 · `harness-rules.md`)

## 배경 / 문제

현재 `/harness-init` 의 기술문서 산출물은 `docs/` 루트에 **평면 3종**(`ARCHITECTURE.md`·
`code-style.md`·`onboarding.md`)으로 떨어진다. 운영하며 드러난 결함:

1. **구조 부재** — 분류 폴더·전체 인덱스(README)가 없어 문서가 늘면 탐색이 어렵다.
2. **요구사항 문서 누락** — PRD(기능/비기능 요구사항)가 없어 "무엇을 왜 만드는가"의 SSOT가 없다.
3. **code-style 이 얕다** — 단일 파일이라 다중 언어/프레임워크 프로젝트에서 스택별 컨벤션이 뭉개진다.
4. **리서치 증거가 호스트에 안 남는다** — `.harness/research/`(gitignored)에만 있어 팀이 못 본다.
5. **버전 호환성 미검증** — 실폴더 스캐폴딩 opt-in 산출물이 감지된 실제 패키지 버전의 공식
   작성법과 어긋나도(예: `tsc -b` 빌드인데 `tsconfig.json` 에 `references` 없음; 루트
   `vite.config.ts` 가 어느 프로젝트 scope 에도 안 잡힘) 걸러지지 않는다.
6. **중간 사본이 남는다** — `.harness/` 의 편입 사본이 정리되지 않아 재실행/업데이트 시 혼란.
7. **스킬 골격이 빈약** — 생성 스킬이 `SKILL.md` 단일 파일뿐, `references/`·`examples/` 가 없어
   Progressive Disclosure 가 안 된다.

## 목표

산출 문서를 분류별 폴더 + 인덱스로 재구조화하고, PRD 를 추가하며, code-style 을 스택별로
분리하고, 리서치를 호스트로 편입하고, 버전 호환성 검증과 편입 사본 정리를 추가한다. 생성
스킬은 보조 폴더(references/examples)를 동반한다. **커맨드 미생성·덮어쓰기 금지·미리보기 후
확정·FAIL-OPEN 등 기존 불변식은 모두 보존한다.**

## A. 산출 문서 구조 — `docs/` 분류별 폴더화

### 목표 레이아웃

```text
docs/
  README.md                  전체 문서 인덱스(구조 한눈에) · 가장 마지막 작성
  prd/README.md              기능/비기능 요구사항 상세 · greenfield 전용 · 가장 먼저 작성
  architecture/README.md     구조 설명 + Mermaid 구조도(필수)
  code-style/
    README.md                스택 인덱스 + 공통 원칙
    <stack>.md               스택별 컨벤션(BP·안티패턴 상세, 코드 스니펫 제외)
  research/
    README.md                리서치 요약 인덱스
    <topic>.md               .harness/research/ 에서 편입(출처 링크 필수)
  onboarding/README.md       실행/디버그 + 주요 문서 링크 모음 · 가장 마지막 작성
```

### 규율

- **각 분류 = 폴더, 진입 문서 = `README.md`** (GitHub 폴더 렌더링 친화적). 단일 문서 분류도 폴더 안에 둔다.
- **작성 순서**: `PRD → research → architecture → code-style → onboarding → docs/README`.
  PRD 가 가장 먼저(무엇을·왜). **research 는 architecture·code-style 의 입력(근거)이므로 그 앞에**
  편입한다 — 그래야 architecture/code-style 이 이미 편입된 `docs/research/` 를 출처로 링크할 수 있다.
  onboarding·전체 README 가 가장 마지막(다른 문서를 링크해야 하므로).
- **PRD 는 greenfield 전용** — brownfield 에선 코드 역산의 위험을 피해 PRD 를 만들지 않고
  ARCHITECTURE·code-style·onboarding·research·README 만 생성한다.
- **출처 링크 의무화** — 모든 문서는 참조한 research 문서/외부 URL 을 마크다운 링크로 단다.
  근거 없는 문장은 "출처 미확인"으로 표기(추측 금지, 기존 원칙 유지).
- **brownfield 기존 `docs/` 관례 존중** — 이미 다른 구조(`documentation/` 등)면 그쪽을 우선하고
  누락 분류만 추가한다(기존 tech-doc-guide 원칙 유지).

### code-style — 스택별 분리

- 파일명 = `<language>` 또는 `<language>-<framework>`(또는 플랫폼). 예: `typescript-react.md`·
  `typescript-express.md`·`python-fastapi.md`·`go.md`·`swift-ios.md`. `harness_scaffold.py` 의
  `detect_frameworks` 결과를 파일 슬롯으로 매핑한다.
- **같은 언어여도 프레임워크/플랫폼이 다르면 파일을 나눈다** — React(컴포넌트/훅/JSX)와
  Express(미들웨어/라우터/에러핸들링)는 강조점이 달라 한 파일로 묶으면 둘 다 얕아진다.
- 각 스택 파일은 **네이밍·포맷·임포트 순서 / 베스트 프랙티스 / 안티패턴(바퀴 재발명 포함) /
  reuse 후보**를 산문으로 상세히 기술한다. **코드 스니펫은 넣지 않는다**(서술로 규율을 전달).
- `code-style/README.md` 는 스택 목록 링크 + 모든 스택 공통 원칙(출처 표기 등)만 둔다.
- **SSOT 분리 유지** — 구조적 위치(폴더/스키마 레이아웃)는 룰(`<framework>-conventions.md`),
  행위적 스타일은 `docs/code-style/<stack>.md`. 룰은 docs 를 가리키되 내용을 복제하지 않는다.

### architecture — Mermaid 필수

- `architecture/README.md` 는 스택/버전 + 폴더 구조 + 주요 모듈/데이터 흐름과 함께 **Mermaid
  구조도(컴포넌트/모듈 관계, 최소 1개)** 를 포함한다. 가능하면 데이터 흐름도 추가한다.
- 리서치/스캔으로 확인한 사실만 다이어그램화한다(추측 노드 금지, 모르면 생략).

### onboarding — 마지막 + 링크 허브

- `onboarding/README.md` 는 실행/디버그에 더해 **"처음 온 사람을 위한 주요 문서 링크"** 절을
  둔다(PRD·architecture·code-style·research 로의 링크). 다른 문서가 다 작성된 뒤 마지막에 쓴다.

## B. 리서치·검증 강화 — 설정 방법 수집 + 버전 호환성 대조

> **핵심 원칙: 툴체인은 "한 세트"로 판단한다.** 빌드러너·컴파일러·번들러·타입체커·린터·테스트러너는
> 서로 맞물린 하나의 세트다. **리서치·검증 모두** 개별 설정파일을 따로 보지 말고 **상호 정합성**(예:
> `tsc -b`(references) ↔ 번들러 include scope ↔ 각 하위 tsconfig)을 세트로 본다.
>
> **만들 때(생성)는 지어내지 말고 권위있는 출력을 복제한다.** 실폴더 스캐폴딩·설정파일을 생성할 때,
> 손으로 설정을 추론해 짜맞추지 않고 **감지된 프레임워크의 공식 스캐폴딩 도구**(예시: Vite→
> `npm create vite@latest`, Next.js→`create-next-app`, Django→`django-admin startproject`)가
> 생성하는 출력을 authoritative baseline 으로 복제한 뒤 프로젝트에 맞게 조정한다(reuse-first 의
> 설정판). 도구 이름은 **예시일 뿐, 산출물에 특정 도구를 단정하지 않는다** — 실제로는
> detect/research 가 정한 프레임워크의 공식 스캐폴더를 쓴다(기존 "라이브러리·도구 단정 금지" 유지).
> "한 세트로 보는 것"은 리서치·검증의 시각이고, "권위 출력 복제"는 **생성 시점의 행위**다.

### B-1. 리서치 항목 확장 (`harness-researcher`)

- **언어/프레임워크/플랫폼별 설정 방법(config)을 버전별로 명시 수집**한다 — 빌드/번들러
  (tsconfig·vite·webpack·tsc 모드)·타입체크·린트/포맷(eslint·prettier·ruff)·테스트 러너
  (jest·vitest·pytest)·패키지 매니저·환경변수/시크릿 관리 등 **실제 설정파일 작성법**을 출처와 함께.
  이 정보가 architecture/code-style/onboarding 문서와 `version-compat` 검증의 **대조 기준**이 된다.
- **메이저 버전별 차이/마이그레이션 주의점**을 수집한다(버전에 따라 설정 스키마·빌드 모드·
  기본값이 갈리는 항목). 버전 불일치/불확실은 명시(추측 금지).
- **자율 확장** — researcher 는 고정 체크리스트에 머물지 않고, **프레임워크 특성상 추가로 필요한
  설정 항목을 스스로 판단해 리서치**한다(예: Next.js→라우팅/SSR·이미지 최적화 설정, Django→ORM
  마이그레이션·settings 분리, 컨테이너 프로젝트→멀티스테이지 빌드·헬스체크). 무엇을 왜 추가
  조사했는지 출력에 근거를 남긴다.

### B-2. 검증 (`harness-critic`)
- `harness-critic` 에 새 검토 영역 **`version-compat`** 추가:
  - 감지된 **실제 패키지 버전**의 공식 작성법과 산출물(특히 실폴더 스캐폴딩 설정파일)이 일치하는가.
  - 빌드 스크립트 ↔ 설정 정합성(예: `tsc -b`(project references 모드)면 루트 tsconfig 에
    `references` 필수), 설정 파일이 **어느 프로젝트 scope 에도 안 잡히는 누락**(루트
    `vite.config.ts` 가 `include` 밖) 같은 결함.
- `critique-guide.md`·`harness-rules.md` 에 동일 규율을 SSOT 로 반영. `version-compat` 를
  critic 출력 스키마의 `kind` enum 에 추가.
- 이 검증은 **게이트가 아니라 진단**(FAIL-OPEN) — high 이슈는 미리보기/보고에 노출하되 차단하지 않는다.

## C. 정리(cleanup) — apply 후 편입 사본 제거

- `harness_scaffold.py` 에 **`cleanup` 서브커맨드** 신설:
  - 인자: `--root`.
  - 동작(화이트리스트·안전): `.harness/research/` 처럼 **docs 로 편입 완료된 중간 사본**만 제거.
  - **보존(절대 삭제 금지)**: `plan.json`·`manifest.json`·`critic-report.json`·`rationale.md`
    (호스트로 복사되지 않은 감사용 증거). 이 파일명 화이트리스트를 코드 상수로 둔다.
  - `.harness/` 자체와 보존 대상은 남기고, 편입 사본 디렉터리만 정리한다.
- **링크 가드(FAIL-SAFE)**: 제거 전 `docs/` 의 `.md` 를 스캔해 **`.harness/research` 를 참조하는
  링크가 있으면 제거를 보류**하고 `link_warnings` 로 보고한다(편입이 잘못돼 링크가 깨질 상황을 막는다).
  참조가 없을 때만(=출처가 모두 `docs/research/` 를 가리킬 때만) 제거한다.
- **예방 규율(authoring)**: 문서의 출처 링크는 편입 위치 `docs/research/` 를 가리킨다 — gitignored
  증거인 `.harness/` 경로를 산출물에서 참조하지 않는다.
- `harness-init/SKILL.md` 의 apply(Step 7) 직후 새 Step 에서 `cleanup` 을 호출하고 보고에 명시.

## D. 스킬 생성 보강 — references/examples 동반

- 생성 스킬은 `SKILL.md` 단일 파일이 아니라 **`<skill>/references/`·`<skill>/examples/`** 보조
  폴더와 최소 사례를 함께 생성한다(Progressive Disclosure).
- `skill-writing-guide.md` 에 "보조 폴더 동반" 규율과 `examples/` 작성법(입력/출력 사례)을 추가하고,
  `harness-authoring/SKILL.md` 의 스킬 산출 절차에 보조 폴더 골격 생성 단계를 넣는다.
- 단순 스킬에 보조 폴더를 강제해 오버엔지니어링하지 않도록 "역할상 분리할 참조/사례가 있을 때"
  조건을 명시(YAGNI).

## E. tsconfig 버그 — B 축 검증의 구체 사례

`tsconfig`/`vite.config.ts` 결함은 템플릿이 아니라 **실폴더 스캐폴딩 opt-in 시 모델이 즉석
생성**한 산출물의 품질 문제다. 별도 템플릿을 만들지 않고 **B 축 검증 규율**(`version-compat`)로
차단한다: `tsc -b` ↔ `references` 정합, 번들러 설정의 프로젝트 scope 포함 여부, tool 모드 일관성.

## 영향 범위 (변경 파일)

| 파일 | 변경 |
|------|------|
| `skills/harness-authoring/templates/prd.template.md` | **신규** — 기능/비기능 요구사항 골격 |
| `skills/harness-authoring/templates/docs-readme.template.md` | **신규** — 전체 인덱스 골격 |
| `skills/harness-authoring/templates/architecture.template.md` | Mermaid 블록 추가 |
| `skills/harness-authoring/templates/code-style.template.md` | 스택별 분리 구조 + 스니펫 제외 + BP/안티패턴 상세 + README 인덱스 |
| `skills/harness-authoring/templates/onboarding.template.md` | 주요 문서 링크 허브 절 추가 |
| `skills/harness-authoring/templates/skill.template.md` | references/examples 보조 골격 안내 |
| `skills/harness-authoring/SKILL.md` | 산출물 목록·작성 순서·폴더 구조·스킬 보조폴더 절차 갱신 |
| `skills/harness-authoring/references/tech-doc-guide.md` | 폴더 구조·PRD·스택 분리·Mermaid·출처·onboarding 링크 규율 |
| `skills/harness-authoring/references/skill-writing-guide.md` | references/examples 동반 규율 |
| `skills/harness-authoring/references/critique-guide.md` | `version-compat` 검토 항목 추가 |
| `skills/harness-init/SKILL.md` | research→docs 편입·cleanup Step·산출 구조 반영 |
| `rules/harness-rules.md` | 문서 구조·PRD·버전 호환성·cleanup·스킬 보조폴더 규율 |
| `agents/harness-critic.md` | `version-compat` 검토 영역 + 출력 enum |
| `agents/harness-researcher.md` | 설정 방법(config) 버전별 수집 + 자율 확장 + 호환성 수집 보강 |
| `scripts/harness_scaffold.py` | `cleanup` 서브커맨드 신설 |
| `tests/test_harness_scaffold.py` | `cleanup` 테스트 추가(보존 화이트리스트 검증 포함) |

## 보존할 불변식 (회귀 금지)

- 커맨드 미생성 · `.claude/commands/` 산출 금지.
- 덮어쓰기 금지(마커 upsert / 부재 시 create) · 미리보기·확정 전 쓰기 금지.
- 검증은 진단(FAIL-OPEN), 게이트 아님 · 지어내지 않음 · 모호하면 질문(Karpathy).
- `${CLAUDE_PLUGIN_ROOT}`=읽기 / `${CLAUDE_PROJECT_DIR}`=쓰기 이중 경로.
- 필수 룰 5종 baseline 마커블록 주입 · 앵커 보존 · marker content 에 BEGIN/END 미포함.
- Windows 인코딩 방어(`force_utf8_io`·`encoding="utf-8"`).
- flow 감지 시 프로세스/커밋 규율은 risk-tiers 로 defer.

## 비목표 (YAGNI)

- 슬래시 커맨드 생성 — 영구 금지.
- tsconfig/vite 등 실설정 템플릿 신설 — 검증으로 대응, 템플릿화 안 함.
- 단순 스킬에 보조 폴더 강제 — 필요할 때만.
- brownfield PRD 자동 생성 — 범위 밖.
