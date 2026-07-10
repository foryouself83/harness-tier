# harness-deployments 스킬 — 설계 (rev.3 오케스트레이터 + 최소-config 스키마)

- **날짜**: 2026-07-10 (rev.3)
- **상태**: rev.1(per-target `workflow_run`) 구현됨(Tasks 1–9) → rev.2(오케스트레이터, 같은 런
  `workflow_call`) 재설계 → **rev.3**: config 스키마 개편(`kind`+`stack`+`secrets` → 단일 `target`+`auth`),
  "config는 파생 불가능한 값만" 원칙, JVM 발행 통합(`maven-central`+`build_tool`), 두 오케스트레이터 버그 수정.
  아직 rev.2/rev.3 **코드 미커밋** — 이 문서가 재구현의 SSOT.
- **범위**: harness-tier 플러그인 — 새 대화형 스킬(`/harness-deployments`) + `github/` 워크플로우 템플릿 +
  `deploy:` 설정 블록 + release 템플릿 통합. 기존 `/flow-init` 기반 위에 얹는 계층.

## 0. 개정 이유 (why orchestrator + why rev.3 schema)

**rev.2(오케스트레이터)**: rev.1은 타깃마다 독립 `deploy-<name>.yml`을 만들고 각자 `workflow_run`(릴리스
완료)로 자동 트리거했다. 동작은 하지만 (1) `workflow_run`은 deploy 파일이 default 브랜치에 있어야 발동하고
크로스-워크플로우 트리거 특유의 취약성이 남고, (2) 타깃 간 **배포 순서 제어가 불가**(전부 병렬)했다. rev.2는
**release.yml이 `deploy.yml`을 같은 런에서 `workflow_call`로 호출** → 크로스-워크플로우 이벤트가 없어
`GITHUB_TOKEN` 재귀/RELEASE_TOKEN 문제가 통째로 사라지고, 오케스트레이터 안에서 `needs:`로 순서를 표현하며,
이미지 타깃에 per-target `context`/`dockerfile`을 준다.

**rev.3(스키마 개편 + 정합성 수정)**:

- **`kind`+`stack`+`secrets` → 단일 `target`+`auth`.** (kind,stack) 2축은 실제로 템플릿 1개를 가리키는
  복합 키일 뿐이고 `registry`+`docker` 같은 무의미 조합을 허용했다. `target: pypi|npm|maven-central|nuget|
  cratesio|ghcr|dockerhub|custom`으로 접으면 템플릿과 1:1이고 오류 조합이 사라진다. `secrets: []`(빈 리스트=
  OIDC)의 암묵 규칙은 `auth: oidc|token`으로 명시화.
- **"config는 파생 불가능한 값만" 원칙.** 렌더러(`--render-deploy`)는 config만 읽고 repo를 못 본다. 그래서
  파생 가능값은 (a) **렌더러가 기본값으로 채움**(image명·context·dockerfile·build·version) → config에서
  **생략 가능(optional)**, (b) **렌더러는 못 만들지만 스킬이 repo에서 감지**(`build_tool`) → **스킬이 감지해
  config에 기입, 사용자엔 안 물음**. 진짜 파생 불가(`enable`·`name`·`target`·`order`·`auth`·custom
  `permissions`)만 사람이 정한다.
- **JVM 발행 통합.** rev.2의 별도 `("registry","gradle")` 매핑을 폐기하고 `target: maven-central` 하나 아래
  `build_tool: maven|gradle|sbt`로 통합. maven·gradle은 **동일한 ASCII-armored GPG 시크릿**을 공유(§6.4),
  sbt만 base64 `PGP_SECRET`로 분리 → sbt는 정적 템플릿이 아니라 reference 저작 경로.
- **오케스트레이터 버그 2건 수정**(§4·§10): (1) `target` 필터를 `workflow_call`·`workflow_dispatch` 양쪽에
  `default: all`로 선언(안 하면 release가 부를 때 전 배포 job이 조용히 스킵), (2) 이미지 `file:`은 빈 값 금지
  — 렌더러가 `<context>/Dockerfile`을 계산해 항상 비어있지 않게 emit(빈 `file:`은 build-push-action 기본값을
  억제).

대가: release 템플릿 6종에 deploy 호출 job이 (활성화 시) 들어가고, deploy 실패가 release 런에 묶인다(단
tag/release는 먼저 만들어지고, 수동 재배포로 보완).

## 1. 목표

하네스에 **배포 계층**을 추가한다. 현재 모든 릴리스 워크플로우는 **태그 + GitHub Release + changelog만**
만들고 산출물을 발행하지 않는다. `/harness-deployments`가 호스트 stack/산출물을 **감지**하고, 타깃을 **질문**하고,
배포 CI(오케스트레이터 + 컴포넌트) + `deploy:` 설정 + release 통합 + 운영 문서를 **생성**한다. 실제 배포는
CI가 실행하며, 플러그인은 호스트에서 직접 배포하지 않는다.

## 2. 배경 — 현재 상태

- **릴리스 = 태그 + 노트만.** 5개 `release.*.workflow.example.yml` + repo 자체 release.yml 전부 산출물 미첨부.
- **JReleaser / 레지스트리 도구는 빌드하지 않는다.** 발행 전 빌드 스텝이 선행해야 한다(release-only 전제).
- **하네스는 CI 워크플로우 중심.** `versioning`/`contract_test`/`unit_test`는 flow-config 블록 → flow_init_setup.py 렌더.
- **왜 크로스-워크플로우 트리거를 피하나(배경).** 기본 `GITHUB_TOKEN`으로 만든 Release/tag는 다운스트림
  `release:published`/tag-`push` 워크플로우를 트리거하지 않는다(예외: workflow_dispatch/repository_dispatch).
  이 취약성 때문에 rev.2/rev.3은 **같은 런 `workflow_call`**을 택한다.
  출처: <https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow>,
  <https://docs.github.com/en/actions/concepts/security/github_token>.

## 3. 결정 사항

| 질문 | 결정 |
|----------|----------|
| 배포 범위 | A+B+C 적응형 — 스킬이 감지+질문 후 필요한 슬라이스만 구현 |
| 산출물 모델 | CI 워크플로우 + `deploy:` 설정 + release 통합 + 문서. CI가 배포 실행(플러그인은 직접 배포 안 함) |
| **트리거/구조 (오케스트레이터)** | `release.yml`이 `deploy.yml`을 **같은 런 `workflow_call`**로 호출 → 크로스-워크플로우 트리거·PAT 불필요. 타깃은 `on: workflow_call` **재사용 컴포넌트**(`deploy-<name>.yml`), `deploy.yml`이 N개 `uses:` job으로 묶고 `needs:`로 순서 제어 |
| **config 스키마 (rev.3)** | `kind`+`stack`+`secrets` → **단일 `target` + `auth`**. **config는 파생 불가능한 값만**(렌더러가 채울 수 있는 값은 생략, 스킬이 감지하는 `build_tool`만 기입) |
| **JVM 발행 (rev.3)** | `target: maven-central` + `build_tool: maven\|gradle\|sbt`. maven·gradle = ASCII-armored GPG 공유(정적 템플릿), sbt = base64 `PGP_SECRET`(reference 저작) |
| 수동 재배포 | `deploy.yml`의 `workflow_dispatch`(tag·target 입력); 각 컴포넌트도 standalone `workflow_dispatch` 보유 |
| 생성 전략 | 하이브리드 — registry/image 컴포넌트는 정적 템플릿(결정적·테스트), 오케스트레이터 `deploy.yml`은 targets에서 **동적 생성**, custom/app-deploy는 references로 저작 |
| release 통합 (rev.3 개정) | 6개 release 템플릿에 정적 `outputs.tag` + `# __HARNESS_DEPLOY_BEGIN/END__` **관리 블록**(주석 마커). **스크립트**(`integrate_release_deploy`)가 블록을 deploy-call job으로 **멱등 채움/비움**(union 권한 재계산 포함) — flow-init·`--render-deploy` **양쪽**에서 호출해 재동기화. 마커 없는 **foreign** release.yml은 스크립트가 `[!]` 거부 → **스킬**이 사용자와 diff 확인 후 편집/수동 안내(모델 편집을 rare-case로 격리) |
| 스킬 vs 스크립트 | 스킬=두뇌(감지→Q&A→config 저작·custom 컴포넌트 저작·리서치·문서·스크립트 `[!]` 예외 상담), 스크립트=손(컴포넌트 복사·deploy.yml 생성·release.yml 관리블록 삽입 — **flow-init 재실행 시에도 재동기화**) |
| 순서/의존성 | `/flow-init` 먼저(flow-config) → `/harness-deployments`. 스킬은 flow-config 부재 시 하드 가드 |
| 파일 단위 | 컴포넌트 `deploy-<name>.yml`(타깃당 1개, workflow_call) + 오케스트레이터 `deploy.yml`(1개, 생성) |
| 초기 타깃셋 | registry: PyPI·npm·Maven Central(maven/gradle)·NuGet·crates.io / image: GHCR·Docker Hub / custom: reference 저작(ssh·k8s·cloud-run·ecs·sbt) |
| 다중언어/모노레포 | targets[] 다중 엔트리. 이미지 타깃에 per-target `image`/`context`/`dockerfile`(생략 시 파생 기본값) |
| Brownfield | 기존 배포/CI 감지 → 채택/증강/보고, 덮어쓰지 않음 |
| 범위 제외(YAGNI) | 멀티환경 승격 게이트, 롤백 자동화, 클라우드별 인증 심화 |

## 4. 아키텍처 & 데이터 흐름

```
호스트 .github/workflows/ (렌더 결과):
  release.yml
    release: (steps: bump/tag)  outputs: { tag: steps.exposetag.outputs.tag }    # 6종에 output 추가
      # tag 값 = git describe --tags --abbrev=0 (release 직후 실제 태그, 균일·v재조립 안 함).
      # 빈 값(스킵) = 템플릿별 기존 released 신호(before/after)로 게이트. node-sr만 신호 추가. jreleaser/gitversion은 항상 릴리스.
    deploy:  needs:[release]  if: needs.release.outputs.tag != ''                # 스킵 릴리스면 배포 안 함
             permissions: {전 타깃 + custom 합집합}  uses: ./.github/workflows/deploy.yml
             with: { tag: ${{ needs.release.outputs.tag }} }  secrets: inherit   # 실제 태그 verbatim
                              │  (같은 런 workflow_call — 트리거 무결. tag를 런타임 전달, target은 안 넘김→default all)
                              ▼
  deploy.yml (오케스트레이터, 생성)
    on:
      workflow_call:    inputs: { tag(req), target(default: all) }               # ★ target 양쪽 default:all
      workflow_dispatch: inputs: { tag(opt), target(default: all) }              #   (안 하면 call 시 전 job 스킵)
    jobs:
      resolve:   (실행 job, timeout O)  [if github.event_name=='workflow_dispatch': checkout fetch-depth:0] → TAG=inputs.tag||git describe --tags --abbrev=0
                 outputs.tag            # 브랜치 인지(stage→rc, main→stable)·release와 동일. 체크아웃은 수동 dispatch만 → 흔한 경로(release call) 수초
      pypi:      if: inputs.target=='all'||=='pypi'  needs:[resolve]      permissions:{contents:read,id-token:write}  uses: deploy-pypi.yml  with:{tag: needs.resolve.outputs.tag}
      api-image: if: inputs.target=='all'||=='api-image'  needs:[resolve,pypi]  permissions:{contents:read,packages:write}  uses: deploy-ghcr.yml  with:{tag: needs.resolve.outputs.tag}
      ecs:       (custom) if: ...  needs:[resolve]  permissions:{config의 값 verbatim}  uses: ./.github/workflows/deploy-ecs.yml  with:{tag, ...config.with}
                              │ (해석된 실제 태그를 각 컴포넌트에 전달)
                              ▼
  deploy-<name>.yml (컴포넌트)  on.workflow_call.inputs.tag(required) + workflow_dispatch.inputs.tag(required)
    steps: actions/checkout ref: ${{ inputs.tag }}  → 빌드 → 발행/업로드/배포 (target별)   # 자기 해석 안 함(빈값 footgun 없음)
```

**왜 `with: tag`가 필수인가**: `workflow_call`은 새 run/이벤트를 안 만들어 호출된 워크플로우의 `github.sha`가
호출자(release를 촉발한 **pre-bump** 커밋)다. release는 실행 중 bump 커밋·태그를 만들므로, ref 미지정 체크아웃은
태그 없는 이전 커밋을 잡아 **틀린 버전을 조용히 발행**한다. 따라서 실제 태그를 인자로 넘겨 컴포넌트가
`ref: <tag>`로 체크아웃한다. 겸사겸사 release job의 `outputs.tag`가 비면(스킵) deploy job `if:`가 배포를 막는다.

**★ target 필터 버그(rev.3 수정)**: `if: inputs.target == 'all' || == '<name>'`로 dispatch에서 특정 타깃만
배포할 수 있게 하되, `target`을 **`workflow_call`·`workflow_dispatch` 양쪽에 `default: all`로 선언**해야 한다.
release가 workflow_call로 부를 때는 `target`을 안 넘기는데, workflow_dispatch에만 선언돼 있으면 `inputs.target`이
빈 문자열이 되어 **모든 배포 job의 `if`가 거짓 → 배포 전체가 조용히 스킵**된다. 양쪽 default:all이면 안 넘겨도
'all'로 채워져 전 타깃이 실행된다.

**태그 값·빈 값·dispatch UX**: tag 값은 **`git describe --tags --abbrev=0`**(release 스텝 직후 로컬에서 방금
만든 태그 — 도구별 output 편차·`v` 접두사 가정 회피; 우리 템플릿은 마켓플레이스 Action이 아니라 CLI라 native
output 없음). 빈 값(스킵) 판정은 템플릿별 **기존** released 신호(before/after HEAD 차분)를 재사용하고
node-semantic-release만 신호를 새로 추가한다. 수동 dispatch에서 `inputs.tag`가 비면 **오케스트레이터의 `resolve`
job**이 `git describe`로 해석 — `gh release view`(정식만 반환)와 달리 dispatch한 브랜치에서 도달 가능한 최신
태그라 stage→rc·main→stable이 자연히 맞다. 해석을 orchestrator 한 곳에 두어 **컴포넌트 `inputs.tag`는
required**(빈 문자열 footgun 소멸). `resolve`는 실행 job이라 `timeout-minutes`를 갖고, 체크아웃은 inputs-if
취약성(runner #2658/#1602)을 피해 `github.event_name == 'workflow_dispatch'` 게이트로 흔한 경로엔 스킵.

**역할 분담**(flow-init과 동형): 결정적 렌더(컴포넌트 플레이스홀더 치환, 오케스트레이터 동적 생성, release
플레이스홀더 채움)는 `scripts/flow_init_setup.py`가, 대화형 판단(감지·Q&A·custom 저작·문서·기존 release.yml
surgical insert)은 스킬이 담당.

## 5. flow-config `deploy:` 스키마 (rev.3)

**원칙: config는 파생 불가능한 값만.** 아래는 전 필드를 보인 예시이며, 실제 config는 optional 필드를 대부분
생략한다(렌더러가 파생 기본값을 채움).

```yaml
# Deployment (CI only). release.yml calls deploy.yml in the SAME run (workflow_call) — no cross-
# workflow trigger, no PAT. Set up by /harness-deployments. enable:false → not installed.
deploy:
  enable: true
  timeout_minutes: 15             # optional (default 15) — 컴포넌트 실행 job의 timeout
  order: [pypi, api-image]        # optional — 나열 순서대로 needs: 체인. 생략 → 전부 병렬
  targets:
    - name: pypi                  # required — job id (unit_test 규칙: 비우면 job-1, job-2 …)
      target: pypi                # required — pypi|npm|maven-central|nuget|cratesio|ghcr|dockerhub|custom
      auth: oidc                  # optional — oidc | token (기본: 타깃별 권장값. pypi/npm→oidc)
      version: "3.12"             # optional — 런타임 버전(setup-*의 version). 생략 → 템플릿 기본
      build: "uv build"           # optional — 아티팩트 빌드 명령. 생략 → 스택 기본
    - name: api-image
      target: ghcr
      image: "ghcr.io/acme/api"   # optional — 생략 시 ghcr.io/${github.repository}
      context: "services/api"     # optional — 생략 시 "."
      dockerfile: "services/api/Dockerfile"   # optional — 생략 시 <context>/Dockerfile
    - name: central
      target: maven-central
      build_tool: gradle          # required*(스킬 감지 기입) — maven|gradle|sbt. 렌더러가 템플릿 선택에 필요
      version: "21"               # optional — JDK
      publish: "./gradlew publishAndReleaseToMavenCentral --no-configuration-cache"   # required — 무기본값(§6.4)
    - name: ecs                   # custom(롱테일) — 스킬이 deploy-ecs.yml을 reference로 저작
      target: custom
      workflow: ./.github/workflows/deploy-ecs.yml   # required
      permissions: { contents: read, id-token: write }   # required — 오케스트레이터가 verbatim 사용
      with: { cluster: prod }     # optional — 컴포넌트에 추가 전달(tag는 항상 자동 전달)
```

**필드 분류 (required / optional-파생 / 감지-기입):**

| 필드 | 분류 | 비고 |
|---|---|---|
| `enable`·`name`·`target` | **required** | 사용자 의도/선택 — 파생 불가 |
| `order`·`timeout_minutes` | optional | 생략 → 병렬 / 15 |
| `auth` | optional(타깃별 기본) | OIDC 설정 여부는 repo 감지 불가 → 스킬이 물어 persist; 기본 oidc 권장 |
| `build` | optional(스택 기본) | 렌더러가 스택 기본 명령 채움 |
| `version` | optional | 생략 → 템플릿 기본(unit_test와 중복 저장 안 함) |
| `image`·`context`·`dockerfile` | optional(파생 기본) | 단일이미지=`ghcr.io/{repo}`·`.`·`<context>/Dockerfile`, 모노레포만 명시 |
| `build_tool` (maven-central) | **required(스킬 감지 기입)** | 렌더러가 maven/gradle 템플릿 선택에 필요 → 스킬이 `build.gradle`/`pom.xml` 감지해 기입, 사용자엔 안 물음 |
| `publish` (maven-central+`build_tool: gradle/sbt`) | **required·무기본값** | §6.4 auto-publish 함정 — 안전한 범용 기본값 없음. `build_tool: maven`은 해당 없음(템플릿의 `mvn deploy`가 pom의 central-publishing-maven-plugin 설정을 그대로 수행) |
| `workflow`·`permissions` (custom) | **required** | 파생 불가 |

- rev.1의 `trigger`/`release_workflow`/`dispatch` 제거(항상 workflow_call + 항상 workflow_dispatch).
- rev.2의 별도 `stack: gradle` 매핑 제거 → `target: maven-central` + `build_tool`로 통합.

## 6. 파일 배치 & 핵심 세부

```text
github/                                     ← 정적 컴포넌트 템플릿 (on: workflow_call)
  deploy.pypi.workflow.example.yml          (target pypi)
  deploy.npm / .nuget / .cratesio .workflow.example.yml
  deploy.maven-central.workflow.example.yml (target maven-central, build_tool=maven)
  deploy.gradle.workflow.example.yml        (target maven-central, build_tool=gradle — NEW)
  deploy.ghcr / .dockerhub .workflow.example.yml   (image/context/dockerfile 파라미터화)
  release.*.workflow.example.yml            ← __HARNESS_DEPLOY_JOB__ 플레이스홀더 추가(6종)

skills/harness-deployments/
  SKILL.md
  references/  registry-publish/ (jvm-gradle.md·jvm-sbt.md 포함) · container-image/ · app-deploy/ · _trigger-and-secrets.md
             (_trigger-and-secrets: "왜 workflow_call인가" + 컴포넌트=workflow_call로 개정)

scripts/flow_init_setup.py                  ← load_deploy_config · DEPLOY_TEMPLATE_BY_TARGET ·
                                              render_deploy_workflows(컴포넌트 렌더 + deploy.yml 동적 생성) ·
                                              versioning 렌더의 __HARNESS_DEPLOY_JOB__ 채움
tests/test_deploy_render.py
```

오케스트레이터 `deploy.yml`은 **정적 템플릿이 아니라 targets에서 동적 생성**한다. 호스트 쓰기는
`.github/workflows/`·`.claude/harness-tier/config/`·`docs/`로만. **플러그인 디렉터리엔 쓰지 않는다.**

### 6.1 템플릿 매핑 (`DEPLOY_TEMPLATE_BY_TARGET`)

`(kind, stack)` 튜플 딕셔너리를 **`target` 단일 키**로 교체:

```python
DEPLOY_TEMPLATE_BY_TARGET = {
    "pypi": "github/deploy.pypi.workflow.example.yml",
    "npm": "github/deploy.npm.workflow.example.yml",
    "nuget": "github/deploy.nuget.workflow.example.yml",
    "cratesio": "github/deploy.cratesio.workflow.example.yml",
    "ghcr": "github/deploy.ghcr.workflow.example.yml",
    "dockerhub": "github/deploy.dockerhub.workflow.example.yml",
}
# maven-central은 build_tool로 분기: maven→deploy.maven-central, gradle→deploy.gradle,
#   sbt→정적 템플릿 없음(reference 저작). custom도 템플릿 없음(config.workflow가 이미 저작본을 가리킴).
```

### 6.2 이미지 `file:` 기본값 (rev.3 수정)

`docker/build-push-action`은 `file` 미지정 시 `{context}/Dockerfile`을 기본으로 쓴다. 그런데 `file: ""`(빈 값)을
넘기면 그 기본이 **무력화**된다. 따라서 렌더러는 `dockerfile`이 config에 없어도 **빈 값을 내보내지 않고**
`__HARNESS_DOCKERFILE__ = dockerfile or f"{context}/Dockerfile"`로 계산해 항상 비어있지 않은 `file:`을 emit한다
(context 생략 시 `.` → `file: ./Dockerfile`). 모노레포만 config에서 명시 override.

### 6.3 `auth`·권한 도출

오케스트레이터는 타깃별 최소권한을 `target`+`auth`(+custom `permissions`)에서 도출한다:

| target | auth | 호출 job permissions |
|---|---|---|
| pypi·npm·cratesio | oidc | `{contents: read, id-token: write}` |
| pypi·npm·… | token | `{contents: read}` (토큰은 secrets로) |
| maven-central·nuget | token | `{contents: read}` |
| ghcr | (GITHUB_TOKEN) | `{contents: read, packages: write}` |
| dockerhub | token | `{contents: read}` |
| custom | — | config `permissions` **verbatim** |

release의 deploy 호출 job은 이 전 타깃 권한 + custom `permissions`의 **합집합**을 상한으로 준다.

### 6.4 JVM 발행 — 서명 키 & auto-publish (리서치 검증)

- **서명 키 형식**: maven·gradle은 **동일한 ASCII-armored GPG 시크릿**을 공유한다.
  - vanniktech `signingInMemoryKey` ← ASCII-armored (`gpg --armor --export-secret-keys`).
  - setup-java `gpg-private-key` ← ASCII-armored (동일 명령).
  - sbt-ci-release `PGP_SECRET` ← **base64** (`gpg --armor --export-secret-keys $ID | base64 -w0`) → **별도 시크릿**.
  - → maven/gradle 템플릿은 `MAVEN_GPG_PRIVATE_KEY`(ASCII-armored) 공유, sbt만 `PGP_SECRET`(base64) 분리.
- **auto-publish 함정**: Portal API `publishingType` 기본이 **`USER_MANAGED`**(업로드만, 공개는 포털 수동
  클릭)이고 vanniktech·nmcp·JReleaser·Maven 플러그인 모두 이를 따른다. "업로드만" vs "즉시 영구 공개(되돌릴 수
  없음)"는 빌드 도구 무관하게 사용자가 반드시 명시하는 결정 → 안전한 범용 기본값이 없어 **`publish`는
  required·무기본값**. `publishAndReleaseToMavenCentral`(자동 공개) vs `publishToMavenCentral`(수동) 등을
  사용자가 명시.
- **Gradle configuration cache**: vanniktech는 Maven Central **release** 발행만 config cache 미지원(Gradle
  #22779) → gradle 명령엔 `--no-configuration-cache` 필수. **이 플래그는 Gradle 전용**이며 Maven `mvn deploy`
  명령엔 절대 붙지 않는다(대응 개념 없음).
  출처: <https://vanniktech.github.io/gradle-maven-publish-plugin/central/>,
  <https://central.sonatype.org/publish/publish-portal-api/>,
  <https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md>,
  <https://typelevel.org/sbt-typelevel/secrets.html>.

## 7. 스킬 실행 흐름

1. **가드** — flow-config 부재 시 "먼저 `/flow-init`" 하드 스톱.
2. **감지** — stack(versioning/modules), 산출물(Dockerfile·패키지), **`build_tool`**(build.gradle→gradle,
   pom.xml→maven, build.sbt→sbt), 기존 배포(.github/workflows/*), 시크릿(`gh secret list`).
3. **Q&A(적응형) — 파생 불가능한 것만 묻는다**: 타깃 선택, per-target `auth`(감지 불가), **배포 순서**(order),
   모노레포 이미지의 `image`/`context`/`dockerfile`(단일이면 안 물음), custom 타깃의 `permissions`/`with`,
   brownfield 채택/증강. `build_tool`은 **감지값을 확인만** 하고, `version`/`build`는 생략 가능(기본값 안내).
4. **생성** — `deploy:` 블록 작성(파생값은 스킬이 채워 기입, 나머진 생략) → 컴포넌트 생성(**3계층 폴백**) +
   오케스트레이터 생성 + **release.yml 관리블록 배선**(`flow_init_setup.py --render-deploy` — 모두 스크립트가
   결정적 수행) → `docs/operations/deploy-guide.md` 작성. 스크립트가 legacy/foreign release.yml을 `[!]`로 거부하면
   (§8) 스킬이 그 케이스만 상담(경로 A 재생성 / 경로 B 의미 패치).
   - **3계층 폴백**: (a) 매핑된 target(registry/image) → 정적 템플릿 렌더(신뢰도 최고), (b) references 있는
     custom(app-deploy·sbt) → 레시피 청사진 저작(높음), (c) **references에도 없는 신규 타깃 → `WebSearch`/
     `WebFetch`로 공식 액션·시크릿·OIDC 리서치 후 계약대로 저작 + "검증 필요" 플래그·필요 시크릿 안내**(중간).
     어느 경우든 저작물은 `on: workflow_call(inputs.tag)` + `ref: inputs.tag` + 실행 job `timeout-minutes` +
     타깃 `permissions` 계약을 지키고, config엔 `target: custom` + `workflow`/`permissions`/`with`로 선언해
     오케스트레이터가 균일하게 `uses:` job으로 묶게 한다.
   - 이를 위해 스킬 frontmatter `allowed-tools`에 **`WebSearch`·`WebFetch` 필요**(리서치 계층).
5. **보고** — 생성 파일, 설정할 시크릿(§6.4의 서명 키 형식 주의 포함), release.yml 변경, 충돌.

## 8. release 통합 상세 (오케스트레이터 난점)

release.yml이 deploy.yml을 호출하려면 **두 가지**가 필요하다: (a) release job의 `outputs.tag`(실제 태그
전달 + 스킵 감지용), (b) deploy 호출 job.

**(a) release job tag output** — 6개 release 템플릿의 release job에 추가:
```yaml
  release:
    outputs:
      tag: ${{ steps.exposetag.outputs.tag }}   # 스킵 시 '' (빈 문자열)
    steps:
      # ... (기존 release/tag 생성 — released 신호 산출) ...
      - name: Expose released tag
        id: exposetag
        run: |
          if [ "<released-신호>" = "true" ]; then echo "tag=$(git describe --tags --abbrev=0)" >> "$GITHUB_OUTPUT"
          else echo "tag=" >> "$GITHUB_OUTPUT"; fi
```
- **tag 값 = `git describe --tags --abbrev=0`**(release 직후 로컬에서 방금 만든 실제 태그). 도구별 output 편차·
  `v` 접두사 가정 회피. 우리 템플릿은 마켓플레이스 Action이 아니라 CLI라 native tag output이 없어 이 방식이 균일.
- **빈 값(스킵) 게이트 = 템플릿별 기존 released 신호(before/after)**: python-semantic-release·cargo-release·
  repo release.yml은 이미 있음(재사용); **semantic-release(node)만 before/after HEAD 신호를 새로 추가**;
  jreleaser·gitversion은 항상 릴리스라 빈 값 케이스 없음(`if "true"`).

**(b) deploy 호출 job** — release job 뒤 **관리 블록**(주석 마커) 안에 스크립트가 삽입:
```yaml
  # __HARNESS_DEPLOY_BEGIN__ (managed by /harness-deployments · /flow-init — do not edit inside)
  deploy:
    needs: [release]
    if: ${{ needs.release.outputs.tag != '' }}   # 스킵된 릴리스면 배포 안 함
    permissions: { contents: read, id-token: write, packages: write }   # 전 타깃 + custom permissions 합집합
    uses: ./.github/workflows/deploy.yml
    with: { tag: ${{ needs.release.outputs.tag }} }   # 실제 태그 verbatim(v 재조립 안 함). target은 안 넘김→default all
    secrets: inherit
  # __HARNESS_DEPLOY_END__
```

**주입 경로 = 스크립트 `integrate_release_deploy(host, plugin)` (결정적·멱등, flow-init·`--render-deploy` 양쪽 호출):**
- **Fresh 렌더**: 6개 release 템플릿에 정적 `outputs.tag`(상시) + **빈 관리 블록**(`# __HARNESS_DEPLOY_BEGIN/END__`
  주석만)을 **미리 저작**. `_render_one`이 최초 생성(파일 없을 때).
- **관리 블록 배선**: `integrate_release_deploy`가 **기존** release.yml에서 마커 쌍을 찾아 그 사이를 deploy.enable
  이면 (b) 호출 job으로, 아니면 비움으로 **치환**한다. 마커 기반이라 재실행 시 **union 권한이 targets 변화에
  맞춰 재계산**되고(멱등), `_render_one`의 일회성 소비에 의존하지 않는다. versioning 렌더는 이 배선을 위해 deploy
  config를 로드한다(의도된 렌더 결합).
- **union permissions**는 구성된 targets(auth/target)에서 도출하되 **custom 타깃의 `permissions`도 합집합에
  포함**한다(재사용 워크플로 토큰은 호출자 상한을 못 넘으므로 custom이 `id-token: write`를 요구하면 상한에도 필요).

**legacy/foreign release.yml — 스크립트는 배선하지 않고 `[!]` 거부 → 스킬 상담(§4 역할 분담 = 구문 vs 의미):**
- 대상: **legacy-ours**(구버전 우리 템플릿 — `outputs.tag`·관리 블록 없음; 기존 harness-tier 소비자가 업데이트한
  가장 흔한 케이스) 및 **truly-foreign**(사용자 자작 release.yml). 마커가 없으면 배선 불가.
- **`outputs.tag`를 소급 삽입하지 않는 이유**: "Expose released tag" 스텝은 release/released 신호가 만들어지는
  **위치 뒤**에 놓여야 하는데, 그 위치는 도구·사용자 구조마다 다른 **의미적 판단**이다. 텍스트 앵커(구문)로는 안전히
  넣을 수 없어 잘못 배치하면 태그가 없는 시점에서 `git describe`가 엉뚱한 값을 잡는다. 그래서 스크립트는
  **추측하지 않고 거부**한다(구문만 담당).
- **silent-fail 방지**: 배선이 안 되면 deploy가 flow-config엔 켜져 있는데 실제로는 아무것도 발행되지 않는다. 따라서
  스크립트의 `report_legacy_release_workflow`가 `[!]`로 **결과(자동 배선 안 됨)** + **두 복구 경로**를 크게 알린다:
  - **경로 A(재생성)**: release.yml을 새 템플릿에서 재생성 → 스크립트가 자동 배선(깔끔하나 커스터마이즈 검토 필요).
  - **경로 B(스킬 의미 패치)**: 스킬이 release job을 읽어 `outputs.tag`(의미적 배치) + deploy job + 마커를 **diff
    확인 후** 삽입(커스터마이즈 보존). 이 케이스가 스킬이 release.yml을 편집하는 **유일한** 경로다(의미 판단 필요).
  - **그동안**: 컴포넌트·`deploy.yml`은 이미 생성돼 **workflow_dispatch로 수동 실행 가능** → 배포가 막히진 않고
    자동 배선만 보류.

## 9. 테스트 전략

- **컴포넌트 렌더**: 각 `github/deploy.*.yml`이 `on: workflow_call`(inputs.tag required) +
  `workflow_dispatch`(inputs.tag required) + `ref: ${{ inputs.tag }}` 체크아웃 + `timeout-minutes` + 플레이스홀더
  치환을 갖는지 assert. 이미지: `context`/`dockerfile` 반영 + **`file:`이 비어있지 않음**(생략 시 `./Dockerfile`,
  모노레포 값 둘 다). Gradle: `("maven-central",gradle)` 렌더 → `gradle/actions/setup-gradle` +
  `ORG_GRADLE_PROJECT_*` env + `MAVEN_CENTRAL_*`/`MAVEN_GPG_*` 시크릿 + `publish` 명령 치환.
- **오케스트레이터 생성**: targets → `deploy.yml`이 유효 YAML이고, `resolve` job(git describe + timeout +
  outputs.tag), **`target`이 workflow_call·workflow_dispatch 양쪽에 `default: all`**, 각 타깃당
  `uses:` job + `secrets: inherit` + `needs`에 resolve 포함 + `with.tag == needs.resolve.outputs.tag` +
  **타깃(uses:) job에 timeout-minutes 없음** + 타깃별 permissions + `if: target=='all'||=='<name>'`,
  `order` → `needs:`에 선행 타깃 추가, custom → config `permissions`/`with` verbatim.
- **release 통합**: `__HARNESS_DEPLOY_JOB__` 채움(enable/disable), 합집합 permissions(custom 포함),
  기존 release.yml surgical insert 멱등성.
- **스키마**: `deploy` 파싱(`target`/`auth`/`build_tool`), `enable:false` 미설치.
- **멱등성**: 재실행 중복 없음.
- **custom 저작**: 모델 주도 → references + harness-critic 리뷰로 가드.
- **불변식 회귀**: `test_all_github_workflow_templates_are_valid_yaml`·`_have_timeout` 무회귀
  (release 템플릿에 `__HARNESS_DEPLOY_JOB__` 추가 후에도 pre-render YAML 유효 유지).

## 10. 유지되는 불변식

- 플러그인에서 호스트 런타임 배포 없음 — CI가 실행.
- 플러그인 디렉터리엔 쓰지 않음; 호스트 쓰기는 `.github/workflows/`·`.claude/harness-tier/config/`·`docs/`.
- **`timeout-minutes`는 실행(steps 가진) job에만** — 컴포넌트 `deploy-<name>.yml`의 실제 job과 오케스트레이터의
  `resolve` job. 호출(`uses:`) job(오케스트레이터 타깃 job, release의 deploy job)은 `timeout-minutes` 무효.
- **호출 job의 permissions는 타깃별 최소권한**(§6.3) — `permissions: {}`(빈 권한) 금지(컴포넌트가 권한을 잃어
  실패). release의 deploy 호출 job은 전 타깃 + custom 권한의 합집합. 컴포넌트도 자기 `permissions:` 유지.
- **union permissions는 렌더 산출물이지 config 필드가 아니다 — 사람이 손으로 유지하지 않는다.** targets에서
  계산하므로, 타깃 추가 시 재렌더가 per-target job 권한과 release deploy job의 union을 **동시에** 재계산한다.
  즉 "GHCR 타깃을 추가하고 union 갱신을 잊어 `packages: write`가 빠진다"는 상태가 **구조적으로 불가능**하다
  (타깃 job과 union은 같은 렌더에서 함께 생기거나 함께 없다). GitHub Actions는 체인에서 토큰 권한을 **축소만
  허용**(상향 불가)하므로 최상위 호출자(release deploy job)의 union이 완전해야 한다 — 그래서 이 결정은 사람에게
  묻지 않고 계산한다. `flow-config`의 `deploy:` 블록에 union `permissions` 필드는 **존재하지 않는다**(유일한
  사람-저작 권한은 non-derivable한 custom 타깃의 per-target `permissions`뿐이고, 그것조차 union엔 자동 합류).
- **`target` 필터는 workflow_call·workflow_dispatch 양쪽에 `default: all`** — 한쪽만 선언하면 release가 부를
  때 전 배포 job이 조용히 스킵된다(rev.3 수정).
- **이미지 `file:`은 절대 빈 값 금지** — 렌더러가 `<context>/Dockerfile`을 계산해 항상 emit(빈 값은
  build-push-action 기본값을 억제, rev.3 수정).
- **config는 파생 불가능한 값만** — 렌더러가 채울 수 있는 값(image/context/dockerfile/build/version)은 생략
  가능, 스킬 감지값(`build_tool`)은 스킬이 기입.
- 렌더는 멱등·비파괴. **release.yml deploy 배선은 스크립트가 관리 블록(주석 마커)으로 멱등 수행**(flow-init·
  `--render-deploy` 양쪽 재동기화). **모델(스킬)은 인식된 release.yml을 편집하지 않는다.**
- **스크립트는 `outputs.tag`를 소급 삽입하지 않는다 — legacy/foreign release.yml은 `[!]` 거부 후 스킬 상담.**
  "Expose released tag" 스텝의 위치는 의미적 판단이라 텍스트 앵커로 안전하지 않다(구문=스크립트 / 의미=스킬).
  거부는 **크게(silent-fail 방지)**: 결과(자동 배선 안 됨) + 두 복구 경로(재생성 / 스킬 의미 패치) + 수동 dispatch 안내.
- pre-render 컴포넌트·release 템플릿은 유효 YAML 유지(정적 `on: workflow_call`; 관리 블록은 주석 마커 —
  bare-line 플레이스홀더 금지).

## 11. 열린 질문 / 향후

- 멀티환경 승격(staging→prod deploy)·롤백 자동화 — 향후.
- sbt 정적 템플릿화 여부(현재 reference 저작; 수요 시 승격).
- OIDC trusted publishing을 레지스트리별 기본 경로로 references에 명시.
