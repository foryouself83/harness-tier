# 워크플로 셸 인터폴레이션 차단 — 설계

- **Date**: 2026-07-20
- **Status**: Implemented (도메인 리뷰 PASS-WITH-NITS → nit 전항목 반영)
- **Scope**: harness-tier가 **저작하는 모든 GitHub Actions 워크플로** — `github/*.workflow.example.yml`
  (템플릿) · `.github/workflows/*.yml`(자체 CI) · `scripts/flow_init_setup.py`의
  `_orchestrator_yaml()`(생성기) · `skills/harness-deployments/references/**`(저작 가이드)

## 1. 목표

`run:` 블록 안의 `${{ }}` 컨텍스트 인터폴레이션을 제거하고, **테스트로 재발을 막는다**.

`${{ }}`는 셸이 스크립트를 파싱하기 **전에** 텍스트로 치환된다. 따라서 셸 메타문자를 담은 값은
데이터가 아니라 **코드**가 된다. `env:`에 바인딩해 `"$VAR"`로 읽으면 셸이 그 값을 다시 파싱하지
않으므로 같은 값이 데이터로 남는다.

## 2. 배경 — 왜 "지금은 안전한데" 고치는가

발견 시점의 5개 릴리스 템플릿은 모두 `on: push: branches: [<stable>, <prerelease>]`,
즉 **고정 2브랜치 트리거**였다. `github.ref_name`은 그 둘 중 하나만 될 수 있으므로 실제 인젝션은
성립하지 않았다.

문제는 **방어가 트리거 한 줄에 있고 그 값을 소비하는 스텝에는 없다**는 점이다. 소비자가 태그
push를 추가하거나 `branches: ['release/**']`로 넓히는 순간(템플릿에 흔한 편집) 방어가 사라지는데,
**셸 라인에는 아무 diff도 생기지 않는다**. git은 ref 이름에 공백과 `~^:?*[\`만 금지하므로
`$(...)`·백틱·`;`는 전부 합법이다.

`env:` + `"$VAR"`는 그 방어를 스텝 안으로 옮긴다. 트리거 편집이 닿지 않는 위치다.

### 발견 경과 — 손으로 센 감사가 두 번 틀렸다

| 단계 | 발견 건수 | 놓친 것 |
|------|-----------|---------|
| 손 감사(grep) | 7건 | `github.run_number` 2건을 "정수라 안전"으로 분류 |
| 검사를 **먼저** 작성 → RED | **9건** | 생성기·references는 검사 범위 밖이라 여전히 안 보임 |
| 독립 도메인 리뷰 | **+7건** | 생성기 1건(가장 위험) + references 6건 |

이 표가 §3의 결정 대부분을 설명한다. **"이 값은 안전한가"를 값마다 판단한 것이 실패 원인**이고,
그래서 판단을 없애는 쪽으로 설계했다.

## 3. 결정 사항

| 질문 | 결정 |
|------|------|
| allow-list vs deny-list | **allow-list**(`matrix`·`steps`만 허용). deny-list면 "이 컨텍스트는 안전한가"를 매번 판단해야 하고, 그 판단이 정확히 `run_number` 2건을 놓친 원인이다. 예외를 두는 순간 규칙이 무너진다 |
| `github.run_number`처럼 무해한 값은? | **똑같이 금지.** 정수라 인젝션이 불가능한 것은 맞지만, 그 판정을 허용하면 다음 사람이 다시 판정해야 한다. 비용은 env 2줄 |
| 검사 범위 | **워크플로가 저작되는 3개 표면 전부** — 템플릿 · 자체 CI · 생성기. 파일 glob만으로는 생성기를 볼 수 없다(§4) |
| references 문서는? | **yaml은 수정하되 검사 대상에서 제외.** 산출물이 소비자 저장소에 생기므로 이 저장소의 어떤 테스트도 도달할 수 없다. CLAUDE.md에 미커버로 **명시**한다(침묵시키지 않는다) |
| `steps.gitversion.outputs.semVer`(서드파티 액션 산출물) | **기록하되 배제하지 않는다.** allow-list에 예외 항목을 만들면 다음 사람이 "왜 이것만?"을 다시 판단한다. 주석이 그 판단을 이미 끝내 두는 편이 낫다. 실질 방어는 semver 문자셋 제약 + `continue-on-error` informational echo |
| 컨텍스트 판정 방식 | **"점이 앞서지 않는 식별자"**. "점이 뒤따르는 이름"으로 매칭하면 `toJSON(github)`·`github['event']`·대문자를 전부 놓친다(§5) |
| 미지의 컨텍스트 | **fail-open**(알려진 12개 목록과 대조). GitHub이 새 컨텍스트를 추가하면 목록 갱신 전까지 통과한다 — 한계로 기록 |
| `cargo publish --token` | **플래그 제거.** cargo가 `CARGO_REGISTRY_TOKEN`을 네이티브로 읽으므로 플래그는 시크릿을 argv(러너 프로세스 목록)에 올릴 뿐이다. NuGet은 반대 — `dotnet nuget push`는 변수를 읽지 않아 `--api-key` 유지 |

## 4. 왜 생성기가 가장 위험했나

`_orchestrator_yaml()`이 만드는 `deploy.yml`의 `resolve` 스텝:

```python
'          TAG="${{ inputs.tag }}"',   # 수정 전
```

다른 8건과 성격이 다르다:

- `inputs.tag`는 `required: false, type: string` **workflow_dispatch 입력**이다. GitHub은
  `type: string`에 어떤 검증도 하지 않는다.
- 릴리스 템플릿의 `ref_name`을 지켜주던 **고정 브랜치 트리거가 여기엔 없다**. 즉 잠재적 위험이
  아니라 **도달 가능한 위험**이다.
- 이 잡이 먹이는 하위 잡들은 `secrets: inherit`로 실행된다.
- 그리고 `/harness-deployments`를 쓰는 **모든 소비자 저장소에 배포**된다.

**검사가 이걸 못 본 이유가 설계의 핵심 교훈이다.** 검사를 "`github/*.yml`과
`.github/workflows/*.yml`을 glob한다"로 정의하는 순간, Python 문자열로만 존재하는 이 워크플로는
정의 밖으로 나간다. 대상을 **파일이 아니라 YAML 텍스트**로 바꿔야 한다:

```python
def _run_block_expressions(text: str) -> list[tuple[str, str]]:   # Path 아님
```

이제 생성기 출력이 파일과 **동일한 파서**를 통과한다.

## 5. 컨텍스트 판정 — 두 번 틀린 정규식

| 시도 | 규칙 | 빠져나가는 것 |
|------|------|---------------|
| 1차 | `expr.startswith(("matrix.", "steps."))` | `steps.a.outputs.b \|\| github.event.head_commit.message` — 앞이 허용이면 뒤는 무엇이든 통과 |
| 2차 | `\b([a-z]+)\s*\.` (점이 **뒤따르는** 이름) | `toJSON(github)` · `github['event']` · `GITHUB.actor` |
| 최종 | `(?<![.\w])([A-Za-z_][A-Za-z0-9_-]*)` (점이 **앞서지 않는** 식별자) + `.lower()` | — |

1차가 놓친 `||` fallback은 공격 기법이 아니라 **이 저장소가 이미 쓰는 관용구**다
(`secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN`). 즉 평범한 편집으로 도달한다.

2차가 놓친 `toJSON(<context>)`는 더 나쁘다. 컨텍스트 디버깅의 표준 관용구라 사람이 그대로
붙여넣고, 페이로드는 `github` 컨텍스트 **전체**(= `event.head_commit.message`, PR 제목/본문 포함)다.

최종안은 방향을 뒤집어 셋을 한 번에 닫는다. 부수 효과로 오탐도 사라진다 — `id: env`인 스텝을
참조하는 `steps.env.outputs.x`에서 `env`는 점이 앞서므로 세그먼트로 취급된다.

## 6. 구현 요약

| 파일 | 변경 |
|------|------|
| `github/release.{cargo-release,gitversion,jreleaser}.…yml` | `ref_name`·`run_number` → `REF_NAME`·`RUN_NUMBER` env |
| `github/deploy.{cratesio,nuget}.…yml` | 시크릿 → env. cratesio는 `--token` 제거 |
| `scripts/flow_init_setup.py` | `_orchestrator_yaml`: `TAG_INPUT` env 경유 |
| `skills/harness-deployments/references/**` | kubernetes·ssh-server·rust-cratesio·dotnet-nuget 4개 |
| `tests/test_flow_init_setup.py` | `_disallowed_contexts` + 3개 테스트 |

`github/release.python-semantic-release.…yml`과 `.github/workflows/release.yml`은 **이미 올바른
패턴**이었다. 나머지가 그쪽으로 수렴한 것이지 새 패턴을 만든 게 아니다.

## 7. 검증

- `uv run pytest -q` → 674 passed
- `uv run pre-commit run --all-files` → 전항목 Passed
- 생성기: 렌더 → YAML 파싱 → `TAG_INPUT=""` fallback 발화 → `TAG_INPUT='v1"; echo PWNED; #'`가
  리터럴로 남음(미실행) 4개 경로 확인
- references의 yaml 펜스 4개 파싱 확인(테스트 범위 밖이므로 수동)

## 8. 남은 것 / 한계

1. **references는 검사 밖** — 구조적 한계(§3). 다음 `/harness-deployments` 저작물은 사람 리뷰가
   유일한 방어다.
2. **미지 컨텍스트 fail-open** — `WORKFLOW_CONTEXTS` 목록 갱신에 의존.
3. **`steps.*` 전면 허용** — `steps.gitversion.outputs.semVer` 하나가 서드파티 산출물이다.
   `steps.` 허용을 좁힐 일이 생기면 첫 번째 후보.
4. **cargo 대체 레지스트리** — `CARGO_REGISTRY_TOKEN`은 기본 레지스트리 전용.
   `publish = ["my-reg"]`면 `CARGO_REGISTRIES_<NAME>_TOKEN`이 필요하다(구 `--token`은 무관했음).
