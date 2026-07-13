---
name: harness-deployments
description: Detect the host stack and add a deployment layer on top of the release workflow — interactively pick targets (registry publish / container image / app deploy), then render or author the CI deploy workflow(s), write the flow-config deploy block, and generate the ops guide. Requires /flow-init to have run first.
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Glob, Grep, WebSearch, WebFetch
argument-hint: (none)
disable-model-invocation: true
---

# Harness-Deployments — 배포 계층 셋업

`/flow-init` 이후에 실행한다. 릴리스(태그+노트) 위에 배포(레지스트리 발행·이미지·앱 배포)를 얹는다.
실제 배포는 CI가 실행하며, 이 스킬은 감지·질문·생성만 한다(호스트에서 직접 배포하지 않음).

**오케스트레이터 구조 — 배선은 항상 자동**: `release.yml`이 `deploy.yml`(오케스트레이터, 생성)을
**같은 런에서 `workflow_call`로 호출**한다 — 크로스-워크플로우 트리거·PAT가 필요 없다. `deploy.yml`은
실제 태그를 한 번 해석해 각 타깃 컴포넌트 `deploy-<name>.yml`(`on: workflow_call`)을 per-target
permissions로 호출한다. 이 배선은 **스크립트**(`flow_init_setup.py` `--render-deploy` / `/flow-init`)가
release.yml의 관리 블록에 멱등하게 채운다 — 스킬은 트리거를 묻거나 배선을 편집하지 않는다(유일한 예외는
§3 release 배선의 legacy/foreign `[!]` 상담).

## Path conventions
- 읽기(템플릿/reference): `${CLAUDE_PLUGIN_ROOT}/...`
- 호스트 쓰기: `${CLAUDE_PROJECT_DIR}/.github/workflows/`, `.../.claude/harness-tier/config/flow-config.yaml`, `.../docs/`
- **플러그인 디렉터리엔 쓰지 않는다.**

## Execution

### 0. 가드 (하드 스톱)
- `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/config/flow-config.yaml` 이 없으면 →
  "먼저 `/flow-init`을 실행하라"고 안내하고 중단.

### 1. 감지
- 스택: flow-config의 `versioning.release_tool` / `version_files` / `modules[].checks` 언어.
- 산출물: `Dockerfile` 존재? 패키지 라이브러리(`pyproject.toml`/`package.json`/`Cargo.toml`/`pom.xml`/`*.csproj`)?
- `build_tool`(`target: maven-central`에서만 필요): `build.gradle`/`build.gradle.kts` → gradle,
  `pom.xml` → maven, `build.sbt` → sbt. 렌더러가 maven/gradle 템플릿 중 무엇을 쓸지 이 값으로 갈라지므로
  스킬이 감지해 config에 기입한다(사용자에겐 확인만 시킨다 — 묻지 않는다).
- 기존 배포: `.github/workflows/*` 에서 이미 있는 publish/deploy 스텝(Grep).
- 시크릿: 가능하면 `gh secret list`로 이미 등록된 레지스트리/서명 시크릿을 확인(보고 단계 참고용).

### 2. Q&A (AskUserQuestion, 적응형) — 파생 불가능한 것만 묻는다
- 감지된 후보를 제시하고 배포 타깃을 고르게 한다("Dockerfile 발견 → GHCR? pyproject → PyPI?").
- 타깃별 `auth`(`oidc` | `token` — repo에서 감지 불가. 기본은 타깃별 권장값, 대부분 oidc).
- 배포 `order`(생략 → 전부 병렬 — 여러 타깃 간 순서가 필요할 때만 묻는다).
- 모노레포 이미지 타깃의 `image`/`context`/`dockerfile`(단일 이미지면 묻지 않는다 — 렌더러가 파생
  기본값 `ghcr.io/${{ github.repository }}` · `.` · `<context>/Dockerfile`을 채운다).
- custom 타깃의 `permissions`/`with`(파생 불가 — 오케스트레이터가 verbatim 사용).
- brownfield: 기존 배포 발견 시 채택/증강/교체 중 선택(조용히 덮어쓰지 않음).
- `build_tool`은 감지값을 **확인만** 한다(다시 묻지 않는다). `version`/`build`는 생략 가능하다고
  안내만 하고 강제하지 않는다(생략 → 렌더러가 스택 기본값을 채운다). `maven-central`+`build_tool:
  gradle/sbt`의 `publish` 명령만은 예외 — 안전한 범용 기본값이 없으므로(§6.4 auto-publish 함정) 반드시
  사용자가 명시한다(`build_tool: maven`은 해당 없음 — pom의 central-publishing-maven-plugin 설정을
  템플릿의 `mvn deploy`가 그대로 수행한다).
- **트리거는 묻지 않는다** — release.yml→deploy.yml 배선은 항상 같은 런의 재사용 워크플로 호출이고
  스크립트가 자동으로 배선하므로, 배포 트리거를 고르는 선택지 자체가 없다(rev.1의 트리거 선택 질문은
  폐기).

### 3. 생성
- `flow-config.yaml`에 `deploy:` 블록 작성/갱신(팀 공유·git 추적) — **config는 파생 불가능한 값만**:
  `enable`/`name`/`target`/`order`/`auth`/custom `permissions`는 사람이 정한 값을 기입하고, 렌더러가
  채울 수 있는 값(`image`/`context`/`dockerfile`/`build`/`version`)은 생략, `build_tool`은 스킬이
  감지한 값을 기입한다.
- **컴포넌트 생성 — 3계층 폴백**(신뢰도 순):
  a. **매핑된 target**(registry/image — `pypi`/`npm`/`nuget`/`cratesio`/`ghcr`/`dockerhub`, 그리고
     `maven-central`+`build_tool=maven|gradle`) → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_init_setup.py"
     --render-deploy` 를 호출해 정적 템플릿을 렌더(**플러그인 SOURCE 경로를 직접 호출** — `flow_init_setup.py`는
     `COPY_FILES`에 없어 호스트로 복사되지 않으므로 `${CLAUDE_PLUGIN_ROOT}`에서 실행한다. `${CLAUDE_PROJECT_DIR}/.claude/
     harness-tier/scripts/`의 호스트 카피가 아니다).
  b. **references가 있는 custom/app-deploy**(ssh·kubernetes·cloud-run·ecs) 또는 **sbt**
     (`target: maven-central`+`build_tool=sbt`, 정적 템플릿 없음) → 해당 레시피
     (`references/app-deploy/*.md`, `references/registry-publish/jvm-sbt.md`)를 청사진으로
     `.github/workflows/deploy-<name>.yml`을 직접 저작.
  c. **references에도 없는 신규 타깃** → `WebSearch`/`WebFetch`로 공식 액션·필요 시크릿·OIDC 지원
     여부를 리서치한 뒤 계약대로 저작 + "검증 필요" 플래그 + 필요 시크릿 목록을 보고에 남긴다.
  어느 계층이든 저작물은 다음 계약을 지킨다: `on: workflow_call`(`inputs.tag` required) +
  `workflow_dispatch`(`inputs.tag` required) + `ref: ${{ inputs.tag }}` 체크아웃 + 실행 job에
  `timeout-minutes` + 자기 `permissions:`. config엔 `target: custom` + `workflow`/`permissions`/`with`로
  선언해 오케스트레이터가 균일하게 `uses:` job으로 묶게 한다.
- **오케스트레이터**(`deploy.yml`)는 `--render-deploy`가 targets로부터 동적 생성한다(정적 템플릿이
  아니다) — 별도 스킬 작업 불필요.
- **release 배선은 스크립트가 담당한다**: `--render-deploy`(그리고 `/flow-init` 재실행)가
  `integrate_release_deploy`로 release.yml의 `# __HARNESS_DEPLOY_BEGIN/END__` 관리 블록을 deploy 호출
  job으로 멱등하게 채운다(union permissions 자동 재계산, flow-init 재실행 시에도 재동기화). **스킬은
  release.yml을 편집하지 않는다** — 유일한 예외는 스크립트가 관리 블록 부재(legacy-ours 또는
  truly-foreign)로 `[!]` 거부를 출력할 때뿐이다. 그 경우 스킬은:
  - **경로 A(재생성)**: release.yml을 최신 템플릿에서 재생성하도록 안내 → 스크립트가 자동 배선(간단하지만
    커스터마이즈 검토 필요).
  - **경로 B(의미 패치 — 스킬이 release.yml을 편집하는 유일한 경로)**: release job을 읽어 **released
    신호가 만들어지는 위치 뒤**(도구마다 다른 의미적 판단이라 스크립트는 못 하고 스킬이 판단)에
    `outputs.tag` + `# __HARNESS_DEPLOY_BEGIN/END__` 마커 + deploy 호출 job을 삽입 — **diff를 보여주고
    사용자 확인을 받은 뒤에만** 적용(커스터마이즈 보존).
  - 어느 경로를 택하든 **그동안** 컴포넌트·`deploy.yml`은 이미 생성돼 있어 `workflow_dispatch`(tag 입력)로
    수동 실행 가능 — 배포가 막히진 않고 자동 배선만 보류된다.
- `docs/operations/deploy-guide.md` 작성/갱신 — 아래 내용 참고.

### 4. 보고
- 생성/변경 파일, repo admin이 설정할 시크릿(§6.4 JVM 서명 키 형식 주의 포함), release.yml 변경 여부
  (자동 배선됐는지 / legacy·foreign이라 `[!]` 상담이 있었는지), 발견된 충돌을 요약.

## `docs/operations/deploy-guide.md` 내용
- 설정할 시크릿(타깃별 — `references/registry-publish/*.md`·`references/container-image/*.md` 참고).
  `maven-central`은 `build_tool`에 따라 형식이 다르다: maven·gradle은 ASCII-armored
  `MAVEN_GPG_PRIVATE_KEY`(공유), sbt는 base64 `PGP_SECRET`(별도) — 혼동 시 서명이 조용히 실패한다.
- 배선은 **항상 자동**(release.yml → deploy.yml, 같은 런 `workflow_call`, PAT 불필요)이라는 점.
- 수동 재배포: `.github/workflows/deploy.yml`을 `workflow_dispatch`(tag 필수, target 선택)로 직접 실행.
- 롤백 포인터(타깃별 `references/*.md`의 롤백 섹션 참고).

## Reuse before build
- 각 stack은 공식 액션을 우선 사용(pypa/gh-action-pypi-publish, docker/build-push-action,
  com.vanniktech.maven.publish 등 — references 참조).
- 유료 서비스 권장 시 명시적으로 비용/라이선스를 알린다.
