# 의미기반 커밋 + sha↔버전 통합 관리 설계

- **작성일**: 2026-07-01
- **상태**: 승인됨 (설계) → 구현 계획 대기
- **참조 구현 출처**: `ras_llm`의 `.github/workflows/{release,branch-naming,entropy-check}.yml`,
  `docs/operations/commit-versioning-guide.md`

## 배경 · 동기

vway-kit은 pip/npm 패키지가 아니라 **Claude Code 플러그인**으로, 마켓플레이스
`marketplace.json`의 `source.sha` 핀으로 배포된다. `pin-marketplace-sha.yml`이
`master` push마다 `source.sha`를 HEAD로 갱신하고, Claude Code auto-update는 sha
문자열이 바뀔 때만 재설치한다.

**문제**: sha는 40자 해시일 뿐 의미가 없다 — 소비자는 "0.1 → 0.2"를 구분하지
못하고, 변경 이력·changelog가 없다. "버전이 없으니 관리가 안 된다."

**목표**: sha 핀 위에 semantic 버전(tag + GitHub Release + version 파일)을 얹어
**sha와 version을 함께 관리**한다. 나아가 이 능력을 harness-init·vdev-init로
일반화해 다운스트림 프로젝트도 스택에 맞게 받게 한다.

## 확정된 결정

| 축 | 결정 |
|---|---|
| 생성 주체 | harness-init(스택 릴리스도구 리서치 + 버전가이드 문서) + vdev-init(CI 렌더) **협업** |
| vway-kit 자체 릴리스 | 플러그인용 **커스텀 릴리스 CI** 추가 |
| 브랜치 | `master`→`main` rename, `dev`·`stage`를 main에서 파생, 셋 다 v0.1 동일 HEAD |
| 업데이트 모델 | **강결합(Explicit version)** — plugin.json `version`이 업데이트를 게이팅. feat/fix에 bump. (공식 권장) |
| pin 메커니즘 | marketplace source를 **불변 `sha`로 핀**(가변 태그 ref 금지 — 공급망 무결성, 보안 리뷰 반영). 릴리스 시 release.yml이 `pin-marketplace-sha.py`로 릴리스 커밋에 pin-to-parent. 매-push 핀 워크플로만 폐기(스크립트 유지) |
| 마이그레이션 | Stream B 영역 — vdev-init/harness-init가 호스트 마지막 적용 버전을 읽어 **버전별 멱등 셋업/마이그레이션**. Stream A는 비교 기준 plugin.json `version`만 확립 |
| 커밋 규율 SSOT | 이미 `rules/risk-tiers.md` "Commit Discipline"에 완비 — 유지, 중복 생성 금지 |

### ⚠️ 설계 정정 이력 (plugins-reference 검증 결과)

초기에 "sha 매 push 갱신 + version은 feat/fix에만"(병행)을 고려했으나, plugins-reference
"Version management"는 이를 **binary**로 규정한다: `version` 필드를 매니페스트에 넣으면
**version bump 시에만** 업데이트되고 커밋 push만으로는 전파 안 됨(sha 무시). version을
생략하면 매 커밋 전파(현 방식). **동시 병행 불가.** 사용자 결정: **강결합** 채택.
따라서 아래 A2/A3/A4는 강결합 기준으로 기술한다.

**2차 정정(보안 리뷰)**: 초기 강결합 구현에서 marketplace 핀을 태그 `ref`로 두었으나,
백그라운드 보안 리뷰가 "가변 태그 = 공급망 무결성 위험"을 지적. version 게이팅은 plugin.json
`version`이 담당하고 핀은 "어느 커밋을 가져올지"만 결정하므로 둘은 독립 — 핀을 **불변 sha**로
되돌렸다(release.yml이 릴리스 시 pin-to-parent). 아래 A2/A3는 sha 기준으로 갱신됨.

## 아키텍처 (두 스트림)

Stream A(vway-kit 자체)가 **참조 구현**이 되고, Stream B가 이를 템플릿화·일반화한다.
A를 먼저 완성·검증한 뒤 B로 확장한다.

---

## Stream A — vway-kit 자체 repo (스펙 A)

### A1. 브랜치 전환
- `master → main` rename → `dev`·`stage`를 main과 동일 HEAD로 생성 → origin push
- GitHub 기본 브랜치를 main으로 변경 + 원격 `master` 삭제 (절차 안내; 원격 변경은
  사용자 확인 후 실행).
- 셋 다 v0.1.0 동일 커밋 상태로 시작.

### A2. 버전 SSOT + 핀 방식 (강결합, 불변 sha)
- `.claude-plugin/plugin.json`에 `"version": "0.1.0"` 추가 = **업데이트 게이팅 SSOT**
  (버전 해석 순서 #1; 이게 있으면 marketplace/sha보다 우선). semantic-release
  `version_variables`가 릴리스 커밋 내에서 이 값을 bump한다.
- `pyproject.toml` `version = "0.1.0"` (이미 존재) = 개발 메타데이터. semantic-release
  `version_toml`이 bump하는 write 타깃 겸 계산 기준.
- `.claude-plugin/marketplace.json` plugin `source`는 **`{source:"github", repo,
  sha:"<40자>"}`** (불변 sha) 유지 — 태그 ref로 바꾸지 않는다(공급망 무결성). marketplace
  entry에는 `version`을 두지 않는다(plugin.json이 SSOT).

### A3. `.github/workflows/` (vway-kit 스택 = Python/uv + .md 플러그인)
- **`release.yml`** — main·stage push 시 python-semantic-release로 feat/fix 감지 →
  `version_toml`(pyproject) + `version_variables`(plugin.json) bump → 릴리스 커밋
  `chore(release): vX.Y.Z [skip ci]` + tag `vX.Y.Z`. main이면 이어서 `pin-marketplace-sha.py`
  로 `source.sha`를 릴리스 커밋에 핀하는 후속 커밋(pin-to-parent) + GitHub Release.
  stage는 rc(`X.Y.Z-rc.N`) 프리릴리스(태그·Release만, sha 핀 안 함). `[skip ci]`로 루프 방지.
- **`pin-marketplace-sha.yml`(매-push 워크플로)** — **폐기**. 매 push sha 갱신은 강결합에서
  무의미(version bump만 전파). 핀은 release.yml이 릴리스 시점에만 수행.
  **`pin-marketplace-sha.py` 스크립트는 유지**(release.yml이 재사용).
- **`branch-naming.yml`** — dev/stage/main/feature/*/fix/*/hotfix/*/release/* 검증.
  vway-kit은 PR 미사용 → `push` 트리거로 조정(ras_llm은 pull_request 트리거).
- **`entropy-check.yml`** — vway-kit용 재조정: `scripts/*.py` ruff 복잡도(C901,
  PLR0912, PLR0915) + 파일크기(>500라인) + `*.sh` ShellCheck(훅 런타임 Windows 버그가
  FAIL-OPEN으로 숨는 문제 대응 — CLAUDE.md Invariants #2). 전 step continue-on-error.

### A4. semantic-release 설정 (pyproject.toml `[tool.semantic_release]`)
- `version_toml = ["pyproject.toml:project.version"]`
- `version_variables = [".claude-plugin/plugin.json:version"]` (JSON regex 치환;
  초기값 비어있지 않아야 함 — Task 2가 0.1.0 설정).
- marketplace `source.sha` 동기화는 build_command가 아니라 release.yml 후속 스텝이
  `pin-marketplace-sha.py`로 수행(릴리스 커밋 sha는 커밋 후에만 알 수 있으므로 pin-to-parent).
- `[tool.semantic_release.branches]`: `main`(정식), `stage`(prerelease, `prerelease_token
  = "rc"`).
- `[skip ci]` 커밋 스킵.

### A5. 커밋 규율
- `rules/risk-tiers.md`에 이미 완비 — 신규 문서 생성 금지.
- **필수 보강**: 강결합에선 `docs:`/`chore:`가 전파를 트리거하지 않으므로, rules·skills 등
  **동작에 영향 주는 `.md` 변경은 `feat`/`fix`로 커밋**해야 소비자에게 전파된다는 규율을
  risk-tiers.md Commit Discipline에 한 줄 명시(병행-라벨 폐기로 이 규율이 필수가 됨).

**결과 흐름**: 소비자는 마지막 릴리스 태그 버전에 머문다. main에 feat/fix가 머지→릴리스되면
plugin.json version이 bump되고 marketplace `source.ref`가 새 태그를 가리켜 `/plugin update`
가 갱신을 감지·설치한다. docs/chore-only 변경은 다음 version bump까지 전파 안 됨(의도된 동작).
dev는 릴리스 트리거 안 함(main/stage만).

---

## Stream B — 플러그인 기능 일반화 (확정 설계)

### B1. vdev-config versioning 슬롯 (확정)
`vdev-config.example.yaml`에 `versioning:` 블록 추가. 확정 필드:
- `enable` / `release_tool` (`python-semantic-release` | `semantic-release`)
- `version_files` (file:field 배열) / `branches.stable` · `branches.prerelease`
- `branch_naming.enable` / `entropy.enable` · `entropy.schedule` · `entropy.paths`

`release_tool`은 harness-init 리서치가 스택별로 채우는 슬롯이다.

### B2. `github/` SOURCE 템플릿 4종 (확정)
`api-contract.workflow.example.yml` 패턴대로 `__VWAY_*__` 플레이스홀더:
- `release.python-semantic-release.workflow.example.yml` (Python/uv 스택)
- `release.semantic-release.workflow.example.yml` (Node 스택)
- `branch-naming.workflow.example.yml` (`__VWAY_STABLE__` / `__VWAY_PRERELEASE__` 치환)
- `entropy-check.workflow.example.yml` (`__VWAY_ENTROPY_SCHEDULE__` / `__VWAY_ENTROPY_PATHS__` 추가)

### B3. vdev-init `render_versioning_workflows` (확정)
`scripts/vdev_init_setup.py`에 `load_versioning_config(host)` +
`render_versioning_workflows(host, plugin)` 구현.
- `_RELEASE_TEMPLATES` 딕셔너리로 `release_tool` → SOURCE 파일 매핑 (도구별 분기).
- `branch_naming.enable` / `entropy.enable` 각각 독립적으로 렌더 여부 결정.
- 멱등·비파괴: 대상 파일 존재 시 보고만(덮어쓰기 X). FAIL-OPEN.
- `tests/test_vdev_init_setup.py`에 대응 테스트 추가.

### B4. 버전 감지 + 마이그레이션 골격 (확정)
`scripts/vdev_init_setup.py`에 stdlib-only 구현:
- `_vkey(s)` — SemVer 문자열을 정수 tuple로 파싱해 비교(`re.findall(r"\d+", s)`).
  **알려진 제약**: prerelease 문자열(`rc`, `alpha` 등)은 digit만 추출하므로
  `1.0.0-rc.1`은 `(1, 0, 0, 1)`로 파싱돼 `1.0.0`보다 *크게* 정렬된다(rc가 release
  이후 취급). 현재 `MIGRATIONS = {}`(빈 레지스트리)라 실제 영향은 없으나, 향후
  마이그레이션 등록 시 prerelease 구간 경계를 key로 쓰지 않도록 주의.
- `MIGRATIONS: dict` — 버전 구간별 마이그레이션 레지스트리(현재 빈 골격).
- `plugin_version(plugin)` — `plugin.json`의 `version` 읽기(실패 시 `"0.0.0"`).
- `applied_version(host)` — 호스트 `.claude/vway-kit/.applied-version` 읽기(없으면 `None`).
  마커는 gitignored(`GITIGNORE_LINES`에 자동 포함).
- `apply_migrations(host, plugin, registry)` — `prev < v <= cur` 구간 실행,
  버전 마커 갱신. 마이그레이션 예외는 경고만(FAIL-OPEN).
- `run_setup()`이 `render_versioning_workflows` + `apply_migrations` 를 순서대로 호출.

### B5. harness-init 확장 (확정)
- `rules/harness-rules.md` §13·13-1·13-2: 감지 스택별 릴리스 도구 리서치 규율 추가.
  스택별 기본 후보(Python → `python-semantic-release`, Node → `semantic-release` 등).
- `skills/harness-authoring/references/commit-versioning-guide.md`: authoring 작성
  지침 레퍼런스 추가(Conventional Commits + SemVer + 감지 스택 릴리스 도구 설정;
  티어·커밋 규율은 `risk-tiers.md` defer, 직접 emit 금지).
- harness-init Step 4: `docs/operations/commit-versioning-guide.md` 항상 생성
  (vdev 감지 여부 무관); vdev 감지 시 릴리스 실설정(CI 워크플로)은 `/vdev-init`이 담당
  — 중복 생성하지 않는다.

---

## 불변식 · 제약 (구현 시 보존)

- CLAUDE.md 이중 경로: `${CLAUDE_PLUGIN_ROOT}`=읽기, `${CLAUDE_PROJECT_DIR}`=쓰기.
  Stream B 렌더 산출물은 호스트에 쓴다.
- vdev-init 멱등성(Invariant #5): 워크플로 렌더는 match-then-skip, 중복 추가 금지.
- 커밋 게이트 불변식(FAIL-OPEN, Windows 인코딩 등)은 손대지 않는다.
- Stream A의 CI는 vway-kit이 harness-init/vdev-init로 설치된 게 아니라 **소스 repo**
  이므로 워크플로를 직접 손으로 작성한다(A가 B의 참조 템플릿이 됨).

## 비목표 (YAGNI)

- 다운스트림 프로젝트의 marketplace ref/버전 핀 결합(marketplace·plugin.json은 vway-kit
  고유). B의 렌더 release.yml은 일반 패키지(pip/npm)용 표준 semantic-release.
- dev 브랜치의 정식 릴리스 트리거.
- sha-only 배포 방식 유지(강결합 채택으로 폐기).
- 커밋 규율 문서의 중복 생성(risk-tiers.md가 SSOT).

## 빌드 순서

1. **스펙 A** — 브랜치 전환 → 버전 파일 → semantic-release 설정 → 워크플로 3종 →
   검증. (`/vdev` Dev 티어)
2. **스펙 B** — A를 템플릿화: config 슬롯 → SOURCE 템플릿 → vdev-init 렌더 + 테스트 →
   harness-init 확장.
