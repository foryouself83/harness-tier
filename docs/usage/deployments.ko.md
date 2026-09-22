# 배포

[English](deployments.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

`/harness-deployments` 는 릴리스 워크플로 위에 발행 계층을 얹음: `release.yml` 이 태그를
만들고, `deploy.yml` 이 **같은 실행**에서 `workflow_call` 로 그것을 받아 — 크로스워크플로
트리거도 PAT 도 없이 — 타깃별 컴포넌트로 최소 권한을 갖고 분기함.

```text
/harness-deployments   # 인자 없음 — 대화형
```

`/flow-init` 이 먼저 실행돼 있어야 함(`flow-config.yaml` 이 필요) — 아니면 안내와 함께
멈춤. 순서: `/harness-init` → `/flow-init` → `/harness-deployments`.

## 하는 일

1. **감지** — `versioning.release_tool`/`version_files`/`modules[].checks` 에서 스택,
   `Dockerfile`·`pyproject.toml`·`package.json`·`Cargo.toml`·`pom.xml`·`*.csproj` 같은
   빌드 산출물, JVM `build_tool`(`build.gradle[.kts]` → gradle, `pom.xml` → maven,
   `build.sbt` → sbt), 이미 있는 `.github/workflows/*` 의 배포 단계, 가능하면
   `gh secret list` 로 이미 등록된 시크릿.
2. **질문** — 도출할 수 없는 것만: 감지된 후보 중 배포 타깃, 타깃별 `auth`(OIDC 대 토큰),
   타깃 간 배포 `order`, 모노레포 이미지의 `image`/`context`/`dockerfile`(이미지 하나면
   건너뛰고 도출된 기본값을 씀), 커스텀 타깃의 `permissions`/`with`. `build_tool` 은
   확인만 함. `version`/`build` 는 생략 가능 — 렌더러가 스택 기본값을 채움 — 단
   `maven-central`+`build_tool: gradle` 또는 `sbt` 의 `publish` 명령만 예외: 프로젝트별로
   태스크 이름이 달라 사용자가 직접 말해야 함. 브라운필드 배포 단계는 채택/증강/교체 중
   선택하며 조용히 덮어쓰지 않음. 트리거 질문은 없음 — 배선은 항상 같음.
3. **생성**:
   - `flow-config.yaml` 의 `deploy:` 블록 — 도출할 수 없던 값만 담음;
   - 매핑된 레지스트리/이미지 타깃(또는 `maven-central`+`build_tool: maven`/`gradle`)은
     플러그인의 정적 템플릿으로;
   - 커스텀이나 앱 배포 타깃 중 매칭되는 레시피가 있으면(ssh, kubernetes, cloud-run, ecs)
     또는 `maven-central`+`build_tool: sbt` 는 그 레시피에서 직접 저작;
   - 매칭되지 않는 타깃은 리서치한 뒤 "검증 필요" 플래그와 필요한 시크릿 목록을 달아 저작;
   - 타깃들로부터 생성되는 `deploy.yml` 오케스트레이터;
   - `release.yml` 안의 오케스트레이터 호출 관리 블록 — 레거시나 외부 파일에만, diff를
     확인받은 뒤 재생성;
   - `docs/operations/deploy-guide.md` — 설정할 시크릿, 빌드 도구별 JVM 서명 키 형식,
     수동 재배포, 롤백 지침.
4. **보고** — 생성/변경된 파일, 저장소 관리자가 설정할 시크릿, 발견된 충돌.

## 배선

`release.yml` 은 `outputs.tag` — 생성된 태그, 또는 릴리스가 건너뛰어졌으면 빈 값 — 를
노출하고 같은 실행에서 그것을 오케스트레이터에 넘김. 오케스트레이터는 태그를 한 번
확정해 각 타깃 컴포넌트를 자신의 최소 권한으로 호출함. 태그를 수동 재배포하려면
`.github/workflows/deploy.yml` 을 `workflow_dispatch` 로 `tag` 입력과 함께 실행하고,
하나만 다시 배포하려면 `target` 을 추가로 넘김.

## `deploy` 블록

```yaml
deploy:
  enable: false
  # timeout_minutes: 15        # 컴포넌트 잡 timeout, 기본 15
  # order: [pypi, api-image]   # 나열한 이름은 순차 실행; 생략하면 전부 병렬
  targets:
    - name: pypi
      target: pypi             # pypi | npm | maven-central | nuget | cratesio | ghcr | dockerhub | custom
```

설정에는 도출 불가능한 값만 담음: `enable`, `name`, `target`, `order`, `auth`, 커스텀
타깃의 `permissions`. 렌더러는 생략된 `image`/`context`/`dockerfile`/`build`/`version`
을 채움.

배포는 옵트인이고 릴리스와 분리됨: `deploy.enable` 여부와 무관하게 `versioning.enable` 이
태그와 노트를 만듦.
