# harness-deployments rev.3 (오케스트레이터 + 최소-config 스키마) 재구현 계획

> **For agentic workers:** superpowers:subagent-driven-development 로 실행. rev.1(Tasks 1–9, 커밋됨)을
> **rev.3**로 개정하는 delta 계획이다. rev.2(오케스트레이터)와 rev.3(스키마 개편·최소-config·JVM 통합·버그
> 2건)를 **한 번에** 적용한다. 각 R-task는 기존 파일을 수정하고, spec rev.3을 SSOT로 참조한다.
> SSOT: docs/superpowers/specs/2026-07-10-harness-deployments-skill-design.md (rev.3)

**Goal:** (1) 배포 트리거를 크로스-워크플로우(`workflow_run`)에서 **같은 런 `workflow_call`**로 전환 —
`release.yml`이 오케스트레이터 `deploy.yml`을 호출, `deploy.yml`이 컴포넌트(`deploy-<name>.yml`,
`on: workflow_call`)를 `uses:`로 묶고 `needs:`로 순서 제어. (2) config 스키마를 `target`+`auth` 단일화 +
"파생 불가능한 값만" 원칙으로 개편, JVM 발행을 `maven-central`+`build_tool`로 통합. (3) 오케스트레이터 버그
2건 수정(target default:all 양쪽 / 이미지 file: 빈 값 금지).

**Architecture:** 컴포넌트 템플릿(정적, `on: workflow_call`) + 오케스트레이터 `deploy.yml`(targets에서 동적
생성) + release.yml 통합. 렌더는 `scripts/flow_init_setup.py`, 대화형은 스킬.

## Global Constraints (rev.1 동일 + rev.3)

- 플러그인 디렉터리에 쓰지 않음; 호스트 쓰기는 `.github/workflows/`·`.claude/harness-tier/config/`·`docs/`.
- **timeout-minutes는 실행(steps 가진) job에만** — 컴포넌트의 실제 job + 오케스트레이터 `resolve` job. 호출
  (`uses:`) job(오케스트레이터 타깃 job, release deploy job)은 `timeout-minutes` 무효.
- **permissions는 호출 job에 타깃별 최소권한**(spec §6.3): pypi/npm/cratesio+oidc→`{contents:read,id-token:write}`,
  토큰 레지스트리(maven/nuget/…)→`{contents:read}`, ghcr→`{contents:read,packages:write}`, dockerhub→
  `{contents:read}`, custom→config `permissions` verbatim. `permissions: {}` 금지. release deploy job은
  **전 타깃 + custom permissions 합집합**. 컴포넌트도 자기 `permissions:` 유지.
- **`target` 필터는 workflow_call·workflow_dispatch 양쪽에 `default: all`** — 한쪽만이면 release call 시 전
  배포 job 조용히 스킵.
- **이미지 `file:`은 절대 빈 값 금지** — 렌더러가 `<context>/Dockerfile` 계산해 항상 emit.
- **config는 파생 불가능한 값만** — 렌더러 채움값(image/context/dockerfile/build/version) 생략 가능, 스킬
  감지값(`build_tool`) 기입.
- 렌더 멱등·비파괴·FAIL-OPEN; `_render_one` 재사용. 파일 IO `encoding="utf-8"`; `force_utf8_io()`.
- pre-render 컴포넌트 템플릿은 유효 YAML 유지(플레이스홀더는 `key: __TOKEN__`; bare line 금지 — rev.1 Task 5 교훈).
- **release 통합은 스크립트 `integrate_release_deploy`(관리 블록 주석 마커, 멱등, flow-init·`--render-deploy`
  양쪽)**(spec §8). 스크립트는 legacy/foreign release.yml(`outputs.tag`·마커 없음)을 **`[!]` 거부**(소급 삽입
  안 함 — 의미 판단) → 스킬이 그 케이스만 상담. 모델은 인식된 release.yml을 편집하지 않는다.
- 커밋: 직접 `git commit`, Conventional Commits(영어), 게이트 미설치.

---

## R1: 설정 스키마 rev.3 + 로더

**Files:** Modify `flow-config.example.yaml`(deploy 블록 전면 개편); Modify `scripts/flow_init_setup.py`
(`load_deploy_config`는 dict 반환이라 구조 변경 없음 — 필드 소비는 R2/R3에서); Modify `tests/test_deploy_render.py`.

**변경(flow-config.example.yaml deploy 블록):** spec §5 스키마로 교체.
- `trigger`·`release_workflow`·`dispatch` **제거**; `kind`+`stack`+`secrets` → **`target`+`auth`**.
- optional: `order`, `timeout_minutes`, `auth`, `version`, `build`, `image`, `context`, `dockerfile`.
- maven-central: `build_tool`(maven|gradle|sbt) + `publish`(required·무기본값).
- custom: `target: custom` + `workflow` + `permissions` + `with`.
- 주석에 "config는 파생 불가만"·필드 required/optional·PAT 불필요·§6.4 서명 키 형식 요약.
- 예시 targets: pypi(oidc), api-image(ghcr, context/dockerfile), central(maven-central/gradle/publish).

**테스트:** `load_deploy_config`가 새 스키마를 그대로 dict로 반환(파싱 스모크); `enable:false` → None 취급 유지.

**Commit:** `refactor(deploy): rev.3 config schema (target/auth/build_tool, minimal-config)`

---

## R2: 컴포넌트 템플릿 → workflow_call + version/image 파라미터 + Gradle + 매핑

**Files:** Modify 7 `github/deploy.*.workflow.example.yml`; **Create `github/deploy.gradle.workflow.example.yml`**;
Modify `scripts/flow_init_setup.py`(`DEPLOY_TEMPLATE_BY_KIND_STACK` → `DEPLOY_TEMPLATE_BY_TARGET`;
`render_deploy_workflows` subs); Modify `tests/test_deploy_render.py`.

**변경(각 컴포넌트 템플릿) — 정적 `on: workflow_call` + `workflow_dispatch`, tag required:**
```yaml
on:
  workflow_call:
    inputs:
      tag: { required: true, type: string }
  workflow_dispatch:
    inputs:
      tag: { description: "배포할 태그 (예: v1.2.3)", required: true, type: string }
```
- 체크아웃 `with: { ref: ${{ inputs.tag }}, fetch-depth: 0 }`; `git describe` 휴리스틱 스텝 제거.
- rev.1 `if: workflow_run.conclusion == 'success'` **제거**(호출되면 실행).
- **워크플로 레벨 `permissions:`는 유지**(standalone workflow_dispatch 대비). 컴포넌트에서 제거되는 것은
  `on: workflow_run`과 그 `if` 가드뿐 — `needs`/job-level `uses`/target-filter `if`는 애초에 컴포넌트에 없고
  **오케스트레이터 호출 job(R3)에만** 존재한다. 컴포넌트의 step-level `uses:`(checkout·setup-*·build-push)도 유지.
- 런타임 버전 파라미터화: setup-java `java-version: __HARNESS_VERSION__`, setup-dotnet `dotnet-version:
  __HARNESS_VERSION__`, setup-python/node 동일(렌더러가 타깃 기본값 채움).
- 이미지 템플릿(ghcr·dockerhub): `context: __HARNESS_CONTEXT__`, build-push-action with에
  `file: __HARNESS_DOCKERFILE__` 추가, `tags:` 는 `__HARNESS_IMAGE__` 유지.

**신규 Gradle 컴포넌트(`deploy.gradle.workflow.example.yml`) — 검증된 2025/2026 방식(spec §6.4):**
- vanniktech 플러그인 전제(build.gradle(.kts)에 구성). 명령 = config `publish`(무기본값; 예:
  `./gradlew publishAndReleaseToMavenCentral --no-configuration-cache`).
- `setup-java`(temurin, `java-version: __HARNESS_VERSION__`) + `gradle/actions/setup-gradle@v4`.
- 시크릿 → env `ORG_GRADLE_PROJECT_*`(이름은 Maven 템플릿과 공유): `MAVEN_CENTRAL_USERNAME`→
  `mavenCentralUsername`, `MAVEN_CENTRAL_PASSWORD`→`mavenCentralPassword`, `MAVEN_GPG_PRIVATE_KEY`(ASCII-armored)
  →`signingInMemoryKey`, `MAVEN_GPG_PASSPHRASE`→`signingInMemoryKeyPassword`.
- rev.3 계약(`workflow_call` inputs.tag / `ref: inputs.tag` / timeout / `permissions: {contents: read}`) 준수.
- `publish` 스텝 명령은 `__HARNESS_PUBLISH__`로 치환(빌드+발행 단일 명령).

**변경(매핑·render_deploy_workflows):**
- `DEPLOY_TEMPLATE_BY_KIND_STACK` → **`DEPLOY_TEMPLATE_BY_TARGET`**(spec §6.1): target→템플릿. maven-central은
  `build_tool`로 분기(maven→deploy.maven-central, gradle→deploy.gradle). sbt·custom은 템플릿 없음 → skip 노트.
- rev.1 `on_lines`/`__HARNESS_ON_BLOCK__` 트리거 분기 **제거**(정적 on:). `trigger`/`release_wf`/`dispatch` 로직 삭제.
- subs 재구성: `__HARNESS_TIMEOUT__`(유지), `__HARNESS_BUILD__`(생략 시 타깃 기본), `__HARNESS_IMAGE__`(생략 시
  `ghcr.io/${{ github.repository }}` 등 타깃 기본), **`__HARNESS_VERSION__`**(생략 시 타깃 기본: python 3.12 /
  node 20 / java 21 / dotnet 8.0), **`__HARNESS_CONTEXT__`**(기본 `.`), **`__HARNESS_DOCKERFILE__`**
  (= `dockerfile or f"{context}/Dockerfile"` — **절대 빈 값 아님**), maven-central은 **`__HARNESS_PUBLISH__`**.
- 컴포넌트 dest는 `.github/workflows/deploy-<name>.yml` 유지.

**테스트:**
- rev.1 `test_trigger_*` → 컴포넌트가 `on.workflow_call.inputs.tag`(req) + `on.workflow_dispatch.inputs.tag`(req)
  + `checkout ref: ${{ inputs.tag }}` + **자체 resolve 스텝 없음**으로 교체.
- 이미지: `context`/`dockerfile` assert(모노레포 값·기본값 둘 다) + **`file:`이 빈 문자열 아님**(생략 시
  `./Dockerfile`) assert.
- version 파라미터: config `version` → 렌더 결과에 반영, 생략 시 타깃 기본.
- Gradle: `target=maven-central,build_tool=gradle` 렌더 → `gradle/actions/setup-gradle` + `ORG_GRADLE_PROJECT_*`
  env + `MAVEN_CENTRAL_*`/`MAVEN_GPG_*` 시크릿 + `publish` 명령 치환. `build_tool=maven` → deploy.maven-central.
- 렌더 결과에 `__HARNESS_` 잔여 없음.

**Commit:** `refactor(deploy): components use workflow_call; version/image params + gradle template`

---

## R3: 오케스트레이터 `deploy.yml` 동적 생성

**Files:** Modify `scripts/flow_init_setup.py`(`render_deploy_workflows`에 오케스트레이터 생성 추가);
Modify `tests/test_deploy_render.py`.

**변경:** 컴포넌트 렌더 후, targets에서 `.github/workflows/deploy.yml`을 **생성**:
```yaml
name: deploy
on:
  workflow_call:
    inputs:
      tag:    { required: true, type: string }
      target: { default: all, type: string }     # ★ call·dispatch 양쪽 default:all (안 하면 call 시 전 job 스킵)
  workflow_dispatch:
    inputs:
      tag:    { description: "배포할 태그(비우면 브랜치 최신 — resolve 해석)", required: false, type: string }
      target: { description: "배포할 타깃(all 또는 특정 name)", default: all, type: string }
jobs:
  resolve:                      # 실행 job — timeout-minutes 보유(불변식). 태그 해석 중앙화.
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions: { contents: read }
    outputs: { tag: ${{ steps.r.outputs.tag }} }
    steps:
      - if: ${{ github.event_name == 'workflow_dispatch' }}   # 흔한 경로(release call, event=push)엔 스킵 → 수초. inputs-if 취약성(#2658/#1602) 회피.
        uses: actions/checkout@v7
        with: { ref: ${{ github.ref }}, fetch-depth: 0 }
      - id: r
        run: |
          TAG="${{ inputs.tag }}"
          [ -z "$TAG" ] && TAG="$(git describe --tags --abbrev=0)"
          echo "tag=$TAG" >> "$GITHUB_OUTPUT"
  <name>:                       # 호출(uses:) job — timeout-minutes 금지(무효)
    permissions: { <타깃별 최소권한 — spec §6.3> }
    if: ${{ inputs.target == 'all' || inputs.target == '<name>' }}
    needs: [resolve<, 선행 name>]        # 항상 resolve 포함 + order/per-target needs
    uses: ./.github/workflows/deploy-<name>.yml   # custom은 config.workflow 경로 그대로
    with: { tag: ${{ needs.resolve.outputs.tag }}<, ...custom.with> }
    secrets: inherit
```
- **permissions 도출**(spec §6.3): `auth: oidc` + registry target → `id-token: write`; ghcr → `packages: write`;
  custom → config `permissions` **verbatim**. 워크플로 레벨 `permissions:` 선언 안 함.
- 타깃 job `needs:`는 항상 resolve 포함 + `order`/per-target needs 합침. `if:`로 target 필터.
- custom 타깃: `uses:`는 config `workflow`, `with`에 tag + config `with` 병합, `permissions`는 config verbatim.
- 유효 YAML 직렬화(들여쓰기 정확; `yaml.safe_dump` 또는 결정적 문자열 조립).

**테스트:** targets 2~3개(+custom) config → `deploy.yml` 생성; `yaml.safe_load` 파싱; `resolve` job(git
describe + timeout + outputs.tag); **`target`이 workflow_call·workflow_dispatch 양쪽에 `default: all`**;
각 타깃당 `uses:` + `secrets: inherit` + `needs`에 resolve 포함 + `with.tag == needs.resolve.outputs.tag`;
**타깃(uses:) job에 timeout-minutes 없음**; 타깃별 permissions(oidc→id-token, ghcr→packages); `if:
target=='all'||=='<name>'`; `order` → 선행 needs; custom → config `workflow`/`permissions`/`with` verbatim.
- **권한 자동 계산(사람 개입 없음)**: config에 ghcr 타깃을 추가한 뒤 렌더하면 그 job permissions에
  `packages: write`가 자동 포함, oidc 레지스트리 추가 시 `id-token: write` 자동 포함. config엔 union/per-target
  `permissions` 필드가 없어도 됨(custom 제외) — targets에서 도출됨을 assert.

**Commit:** `feat(deploy): generate deploy.yml orchestrator (target default:all, per-target perms)`

---

## R4: release 통합 — 정적 outputs.tag + 스크립트 관리블록 배선

**Files:** Modify 5 `github/release.*.workflow.example.yml`(+ dogfood 시 repo `.github/workflows/release.yml`);
Modify `scripts/flow_init_setup.py`(신규 `integrate_release_deploy` + `render_versioning_workflows`·
`render_deploy_workflows`에서 호출); Modify `tests/test_deploy_render.py`/`test_flow_init_setup.py`.

**변경(각 release 템플릿) — 정적 `outputs.tag` + 빈 관리 블록:** spec §8.
- release job에 `outputs: { tag: ${{ steps.exposetag.outputs.tag }} }`(상시) + "Expose released tag" 스텝:
  ```yaml
  - name: Expose released tag
    id: exposetag
    run: |
      if [ "<released-신호>" = "true" ]; then echo "tag=$(git describe --tags --abbrev=0)" >> "$GITHUB_OUTPUT"
      else echo "tag=" >> "$GITHUB_OUTPUT"; fi
  ```
  - `<released-신호>`: python-semantic-release·cargo-release·repo release.yml은 **기존** released output 재사용;
    **semantic-release(node)만 before/after HEAD 신호 새로 추가**; jreleaser·gitversion은 항상 릴리스 → `if true`.
  - 이 스텝 위치는 **의미적**(released 신호 산출 뒤)이라 템플릿에 우리가 직접 배치(스크립트가 소급 삽입 안 함).
- `jobs:` 말미에 **빈 관리 블록**(주석 마커 쌍, 항상 유효 YAML):
  ```yaml
    # __HARNESS_DEPLOY_BEGIN__ (managed by /harness-deployments · /flow-init — do not edit inside)
    # __HARNESS_DEPLOY_END__
  ```

**신규 `integrate_release_deploy(host, plugin)` — 결정적·멱등 관리블록 배선:**
- 호스트 `release.yml`을 읽어 `# __HARNESS_DEPLOY_BEGIN__`…`# __HARNESS_DEPLOY_END__` 마커 쌍 사이를:
  deploy.enable이면 **deploy 호출 job**으로, 아니면 **빈 값**으로 치환(마커는 보존 → 재실행 시 재배선). 정확 들여쓰기.
  ```yaml
    deploy:
      needs: [release]
      if: ${{ needs.release.outputs.tag != '' }}
      permissions: { contents: read, id-token: write, packages: write }   # 전 타깃 + custom permissions 합집합
      uses: ./.github/workflows/deploy.yml
      with: { tag: ${{ needs.release.outputs.tag }} }
      secrets: inherit
  ```
- permissions union은 targets(auth/target)에서 도출 + **custom 타깃 `permissions` 포함**(spec §8 말미).
- **`render_versioning_workflows`(flow-init)와 `render_deploy_workflows`(--render-deploy) 양쪽에서 호출** → 재동기화.
- **legacy/foreign 거부**: 마커 쌍이 없거나 release job에 `outputs.tag` 배선이 없으면 **배선하지 않고**
  `report_legacy_release_workflow`가 `[!]`로 (결과: 자동 배선 안 됨) + **두 복구 경로**(A 재생성 / B 스킬 의미 패치)
  + "그동안 deploy.yml은 workflow_dispatch 수동 실행 가능"을 반환한다. **파일은 편집하지 않음**(소급 삽입 안 함 —
  `outputs.tag` 위치는 의미 판단, 텍스트 앵커 불가). FAIL-OPEN(예외 시 배선 skip, release는 무해).

**테스트:** 6 템플릿 pre-render 유효 YAML(빈 관리 블록·정적 outputs.tag 포함); `integrate_release_deploy`
(deploy.enable) → 마커 사이에 `deploy:` job + `needs:[release]` + `if: needs.release.outputs.tag != ''` +
`with.tag == needs.release.outputs.tag` + **호출 job에 timeout-minutes 없음**; deploy.enable=false → 블록 비고
마커 보존; **재실행 멱등**(중복 삽입 없음, targets 변화 시 union 갱신); release job에 `outputs.tag` + "Expose
released tag" 스텝; `_have_timeout`/`_valid_yaml` 무회귀.
- **legacy/foreign**: 마커/`outputs.tag` 없는 release.yml → `integrate_release_deploy`가 **파일 미편집** +
  `[!]` 두 복구 경로 반환(assert). 스킬이 이 상담을 맡음(R5).
- **union은 계산됨(config 필드 아님)**: targets에 ghcr 추가 → union에 `packages: write` 자동, oidc 추가 →
  `id-token: write` 자동, custom `permissions`도 union 합류. `flow-config`에 union `permissions` 필드가 **없어도**
  정확한 상한이 나옴을 assert(그 필드를 두면 사람이 갱신 잊어 체인 상한이 낡음 — 금지).

**Commit:** `feat(deploy): script-driven release integration (managed block + legacy [!] refusal)`

---

## R5: 스킬 · references · 문서 rev.3

**Files:** Modify `skills/harness-deployments/SKILL.md`; Modify
`skills/harness-deployments/references/_trigger-and-secrets.md`; **Create
`skills/harness-deployments/references/registry-publish/jvm-gradle.md`** 및 **`.../jvm-sbt.md`**(sbt base64
PGP_SECRET 저작 경로); Modify `CLAUDE.md`·`USAGE.md`·`USAGE.ko.md`.

**변경(SKILL.md):**
- frontmatter `allowed-tools`에 **`WebSearch`·`WebFetch` 추가**(리서치 계층).
- 감지에 **`build_tool`**(build.gradle→gradle, pom.xml→maven, build.sbt→sbt) 추가.
- Q&A는 **파생 불가능한 것만**(spec §7.3): target·`auth`·order·모노레포 image/context/dockerfile·custom
  permissions/with·brownfield. `build_tool`은 감지값 확인만, `version`/`build`는 생략 가능(안내). rev.1 트리거
  선택(workflow_run/release:published) **제거**.
- §생성을 **3계층 폴백**으로(spec §7.4): (a) 매핑 target 렌더, (b) references 있는 custom(app-deploy·sbt) 저작,
  (c) references에도 없는 신규 → WebSearch/WebFetch 리서치 후 저작 + "검증 필요"·시크릿 안내. 저작물은 rev.3
  계약 준수 + config에 `target: custom`+`workflow`/`permissions`/`with` 선언.
- **release.yml 배선은 스크립트가 함**(R4 `integrate_release_deploy`). 스킬은 스크립트가 `[!]`
  (`report_legacy_release_workflow`)로 거부한 **legacy/foreign 케이스만 상담**(spec §8):
  - **경로 A(재생성)** 안내, 또는 **경로 B(의미 패치)**: 스킬이 release job을 읽어 released 신호 산출 뒤 올바른
    위치에 `outputs.tag`(의미적 배치) + deploy job + 마커를 **diff 확인 후** 삽입(브라운필드 비파괴). 이것이
    스킬이 release.yml을 편집하는 **유일한** 경로.
  - 그동안 `deploy.yml`은 `workflow_dispatch` 수동 실행 가능함을 안내. versioning 비활성으로 release.yml이 아예
    없으면 deploy는 수동 dispatch 전용임을 안내.
- `--render-deploy`(플러그인 SOURCE 경로: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_init_setup.py"
  --render-deploy`) 설명 반영.

**변경(_trigger-and-secrets.md):** rev.3 스토리 — "release가 deploy를 같은 런 workflow_call로 호출 →
크로스-워크플로우 트리거·RELEASE_TOKEN 불필요. 컴포넌트는 `on: workflow_call`(+수동 workflow_dispatch)."
GITHUB_TOKEN 재귀 배경은 "그래서 크로스-워크플로우를 안 쓴다"로 유지. OIDC 우선. §6.4 서명 키 형식(maven/gradle
ASCII-armored 공유, sbt base64) 요약 추가.

**신규 jvm-gradle.md / jvm-sbt.md:** vanniktech(gradle)·sbt-ci-release(sbt) 발행 레시피 — 플러그인 구성, publish
명령(auto vs 수동), 시크릿 형식(§6.4), OIDC 불가(토큰) 안내.

**변경(CLAUDE.md·USAGE·USAGE.ko):** 오케스트레이터 구조(release→deploy.yml→컴포넌트), 순서 제어, 이미지
context, 스키마 rev.3(target/auth), "트리거 무결(PAT 불필요)"로 갱신. USAGE.md 영어, USAGE.ko.md 한글.

**검증:** 스킬 frontmatter parse ok; references 스모크; USAGE grep.

**Commit:** `refactor(deploy): rev.3 skill, references, docs (orchestrator + minimal-config + release integ)`

---

## R6: 전체 검증

- `uv run pytest` 전체 통과(신규/개정 테스트 포함).
- `uv run ruff check && uv run ruff format --check`.
- 모든 `github/deploy.*.yml` + 오케스트레이터 생성물 + release 템플릿이 유효 YAML(기존 불변식 테스트 무회귀).
- `uv run pre-commit run --all-files`.
- **Commit(변경 시):** `test(deploy): rev.3 verification`

## Self-Review (rev.3 스펙 대비)

- 트리거 전환(workflow_call) → R2(컴포넌트)+R3(오케스트레이터)+R4(release).
- 스키마 rev.3(target/auth/build_tool/publish/custom) → R1(스키마)+R2(매핑)+R3(권한 도출).
- 최소-config(파생값 렌더러 기본) → R2(subs 기본값)+R5(스킬 감지·질문 축소).
- JVM 통합(maven/gradle 공유 GPG, sbt reference) → R2(gradle 템플릿·매핑)+R5(jvm-gradle/sbt.md).
- 버그 2건: target default:all 양쪽 → R3; 이미지 file: 빈 값 금지 → R2.
- release 통합(정적 tag output + 스크립트 관리블록 배선 + 합집합 permissions incl custom + legacy `[!]` 거부)
  → R4(스크립트 `integrate_release_deploy`) + R5(스킬은 legacy/foreign 상담만).
- 순서 제어(order→needs) → R3. pre-render YAML 유효성(컴포넌트 정적 on: + release 빈 관리블록) → R2/R4 + 불변식 테스트.
