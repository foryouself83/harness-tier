# vdev-tiers.yaml 을 scripts/ → config/ 로 이동

- 날짜: 2026-06-30
- 티어: DEV (게이트가 정책을 읽는 경로를 바꾸는 변경)

## 배경 / 문제

플러그인 정책 파일 `vdev-tiers.yaml`(tier→gates, 불변)은 현재 `/vdev-init`
실행 시 호스트의 `.claude/vway-kit/scripts/` 로 복사된다(`COPY_FILES` 포함).
설정 파일 `vdev-config.yaml` 은 `.claude/vway-kit/config/` 에 위치한다.

사용자 요청: 두 yaml(정책·설정)을 **같은 `config/` 디렉터리**에 모은다.

## 결정사항

- **목적지**: `vdev-tiers.yaml` 을 `config/` 로 복사한다.
- **폴백**: `tiers_path()` 의 호스트 탐색을 `config/` **단일 경로**로 교체한다
  (기존 `scripts/` 형제 폴백은 남기지 않는다 — 게이트 스크립트와 정책 파일은
  항상 같은 `/vdev-init` 실행으로 함께 배포되므로 "새 게이트 + 옛 위치" 조합은
  발생하지 않는다).
- **마이그레이션**: 기존 호스트는 `/vdev-init` 재실행 시 자동 전환한다.

## 영향 받는 산출물 / 경계

| 항목 | 위치 | 소유 | 추적 |
|------|------|------|------|
| `vdev-tiers.yaml` (정책, 불변) | `config/` (이동 후) | **플러그인**(매 설치 덮어씀) | git 추적 |
| `vdev-config.yaml` (환경값) | `config/` | 호스트(사람이 편집) | git 추적 |

**개념적 마찰**: `config/` 는 "호스트 소유(편집 가능)" 영역인데 정책 파일은
플러그인이 매 설치마다 덮어쓴다. → 주석으로 "편집 금지(플러그인 소유·SSOT)"
임을 명시해 `vdev-config.yaml` 과 구분한다.

## 변경 지점

### ① `scripts/vdev_gate_check.py` — `tiers_path()` 탐색 교체

```
정책 파일 해석 순서:
1. CLAUDE_PLUGIN_ROOT/vdev-tiers.yaml          — 플러그인 hook 직접 실행 (유지)
2. config/ 디렉터리의 vdev-tiers.yaml          — 호스트 복사본 (scripts/ 형제 → config/ 교체)
3. 호스트 루트 vdev-tiers.yaml                 — 폴백(개발/테스트) (유지)
```

- `sibling = Path(__file__).resolve().parent / TIERS_FILENAME`
  → `Path(__file__).resolve().parent.parent / "config" / TIERS_FILENAME`
- `scripts/` 의 형제 디렉터리가 `config/` 이므로 `__file__` 기준 해석을 계승한다
  (`host_root()` 불안정성에 영향받지 않음).
- docstring 의 2번 항목을 "config 디렉터리"로 갱신.

### ② `scripts/vdev_init_setup.py` — 복사 목적지 분리

- `COPY_FILES` 에서 `"vdev-tiers.yaml"` 제거(scripts/ 대상에서 빠짐).
- `copy_artifacts` 가 `vdev-tiers.yaml` 을 `config/` 로 **항상 덮어쓰며** 복사
  (SSOT 단방향 전파 유지).

### ③ `scripts/vdev_init_setup.py` — 마이그레이션

- 기존 호스트의 `scripts/vdev-tiers.yaml` 잔재 제거(`migrate_legacy_paths`
  의 잔재 정리 메커니즘에 통합). config/ 에는 ②가 새로 넣으므로 "이동"이
  아니라 "새 위치 복사 + 옛 위치 삭제".
- 기존 `flow-tiers.yaml` orphan 제거는 그대로 유지.

### ④ 문서·주석·테스트

- `CLAUDE.md`: Folder structure(`scripts/`·`config/` 설명), "호스트 쓰기"
  아키텍처 항목, "정책 vs 환경값" 항목.
- `scripts/_vway_paths.py`: `SCRIPTS_DIR`/`CONFIG_DIR`/`TIERS_FILENAME` 주석.
- `tests/test_vdev_init_setup.py`: COPY_FILES 에 tiers 없음 · config/ 복사 ·
  마이그레이션(scripts/ 잔재 제거) 검증.
- `tests/test_vdev_gate_check.py`: `tiers_path` 가 config/ 를 해석함 검증.

## 검증 (테스트)

- `tiers_path()`: `config/vdev-tiers.yaml` 이 있을 때 그 경로를 반환, 없으면
  호스트 루트로 폴백.
- `copy_artifacts`: `config/vdev-tiers.yaml` 생성, `scripts/vdev-tiers.yaml`
  미생성.
- `migrate_legacy_paths`: 기존 `scripts/vdev-tiers.yaml` 존재 시 제거.
- 기존 게이트 강제 동작(미분류 fail-closed, 정책 파싱 실패 fail-open)은
  회귀 없이 유지.

## Invariant 영향

- Invariant #1(FAIL-OPEN, 미분류·정책부재는 fail-closed): 정책 파일 위치만
  바뀌고 "파싱 성공 판정" 로직은 불변 — 회귀 없음.
- 단방향 전파(SOURCE → 캐시 → 호스트 사본): 목적지 디렉터리만 변경, 방향 유지.

## 비목표 (YAGNI)

- `scripts/` 형제 하위호환 폴백을 두지 않는다.
- `vdev-config.yaml` 등 다른 산출물 위치는 건드리지 않는다.
- 슬래시 커맨드 신규 생성 없음.
