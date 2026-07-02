# commit-versioning-guide 작성 지침

`harness-authoring` 이 `docs/operations/commit-versioning-guide.md` 를 생성할 때 따르는 규율.
**규율 SSOT**: [harness-rules.md](../../../rules/harness-rules.md) §버전/릴리스 컨벤션 리서치(13·13-1·13-2).

---

## 생성 조건

- **항상 생성**(vdev 감지 여부 무관) — 코드스타일+컨벤션 문서 범위이므로 rule 14 defer 대상이 아님.
- 출력 경로: `docs/operations/commit-versioning-guide.md`
- 출처는 `docs/research/` 로 링크(`.harness/` 경로 절대 참조 금지 — cleanup 후 깨짐).

---

## 문서 구조 (섹션 순서)

### 1. Conventional Commits 요약
- 형식: `<type>[optional scope]: <description>` (공식 스펙 링크 필수)
- 주요 type: `feat`(MINOR) · `fix`(PATCH) · `BREAKING CHANGE`(MAJOR) · `chore`/`docs`/`ci`(버전 비영향)
- 출처: <https://www.conventionalcommits.org> (링크 필수)

### 2. SemVer 정책
- `MAJOR.MINOR.PATCH` 의미 설명(출처: <https://semver.org>).
- **0.x 프로젝트 권장 정책**:
  - `major_on_zero=false` — `BREAKING CHANGE` 커밋이 있어도 0.x 유지(1.0.0 우발 승격 방지).
  - annotated 태그 사용: `git tag -a v0.x.y -m "release v0.x.y"` (lightweight 태그보다 changelog 도구 친화적).
  - 1.0.0 승격은 명시적 수동 결정으로만 한다.

### 3. 릴리스 도구 설정 (스택별)
스택이 확정된 경우 해당 도구를 기술한다. **미확정이면 "확인 필요"로 두고 지어내지 않는다(harness-rules 4).**

#### 스택별 기본 도구 후보

| 스택 | 권장 도구 | 버전 파일 |
|------|-----------|-----------|
| Python | `python-semantic-release` | `pyproject.toml` 의 `[tool.poetry] version` 또는 `__version__` |
| Node/TypeScript | `semantic-release` | `package.json` 의 `"version"` |
| Rust | `cargo-release` | `Cargo.toml` 의 `[package] version` |
| Go | `goreleaser` | `go.mod` 태그 기반(파일 버전 없음 — git 태그가 SSOT) |
| 기타 | researcher 가 생태계 표준 조사 후 근거와 함께 제안 | — |

> **라이브러리 단정 금지**: 위 목록은 후보이며, research·code-analyzer 근거 없이 특정 도구를 확정하지 않는다(harness-authoring 원칙).

#### 설정 항목 (도구별로 research 결과로 채운다)
- changelog 생성 여부·파일 위치
- pre/post-release CI 훅
- `vdev-config.versioning.release_tool` 슬롯 제안값
- `vdev-config.versioning.version_files` 슬롯 제안값(파일 목록)

### 4. 버전 확인 명령
```bash
# 현재 태그 기반 버전 확인 (모든 스택 공통)
git describe --tags --abbrev=0

# 릴리스 도구 dry-run (도구 확정 후 채운다 — 스택별)
# Python: semantic-release version --dry-run
# Node:   semantic-release --dry-run
# Rust:   cargo release --dry-run
# Go:     goreleaser release --skip-publish --snapshot
```

### 5. vdev 감지 시 안내
- **vdev 감지** — `commit-versioning-guide` 의 **티어·커밋 규율 내용은** [risk-tiers.md](../../../rules/risk-tiers.md) 로 defer 한다.
  이 문서는 *버전·릴리스 메커니즘*만 기술하고 프로세스 규율(승인·머지·PR 등)은 중복하지 않는다.
- **vdev 미감지** — 릴리스 도구 실설정(CI 워크플로·훅)을 opt-in 으로 제안한다(사용자 동의 시만 생성).

---

## 작성 규칙

1. **출처 URL 필수** — Conventional Commits·SemVer 공식 링크 + 릴리스 도구 공식 docs 링크를 단다.
2. **0.x 정책 명시** — 프로젝트가 0.x 이면 반드시 `major_on_zero=false` + annotated 태그를 권장 절에 기술한다.
3. **티어·커밋 규율 emit 금지** — 승인 흐름·브랜치 전략·PR 규율은 risk-tiers defer 문구만 두고 자체 emit 하지 않는다.
4. **vdev 중복 생성 금지** — vdev 감지 시 `/vdev-init` 이 렌더하는 CI 워크플로·릴리스 훅 실파일은 이 문서에서 생성하지 않는다.
5. **미확정 스택 — "확인 필요"** — 릴리스 도구·버전 파일이 불확실하면 지어내지 않는다(harness-rules 4).
6. **간결** — 문서는 항목당 1~3줄. 장황한 설명보다 구체적 명령/설정값으로.
