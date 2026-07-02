# 모듈별 CLAUDE.md 템플릿

Mode B 가 `service_docs`(모듈별 로컬 CLAUDE.md)를 신규 생성·갱신할 때 따르는 템플릿과 품질 기준.
harness 루트 CLAUDE.md(`skills/harness-authoring/templates/claude-md.template.md` — baseline 원칙·룰
마커 관리)와는 목적이 다르다: 이 템플릿은 **모듈 하나의 실사용 정보**(명령·구조·게치·의존성)만 담고,
프로젝트 전역 작업 원칙은 다루지 않는다.

출처: Anthropic 공식 `claude-md-management` 플러그인(`claude-md-improver` 스킬)의
templates.md·quality-criteria.md·update-guidelines.md.

신규 생성은 harness 가 설치된 프로젝트에서만 한다(`docs/code-style/` 존재 또는 형제 모듈에
이미 CLAUDE.md 존재 — [`vdev-init`](../../vdev-init/SKILL.md)의 harness 감지 신호와 동일).
harness 미설치 프로젝트에 임의 생성하면 그 감지가 오작동한다 — 자세한 판단은
[`doc-sync/SKILL.md`](../SKILL.md) Check item 5 참조.

## 핵심 원칙

- **간결**: 개념당 1줄. 장황한 설명보다 밀도.
- **실행 가능**: 명령은 그대로 복사-붙여넣기 가능해야 한다.
- **모듈 고유**: 이 모듈에만 해당하는 내용만. 일반론·타 모듈과 중복되는 사실 금지(SSOT는 한 곳에만).
- **최신**: 실제 코드 상태를 반영. 존재하지 않는 경로/명령을 적지 않는다.

## 권장 섹션 (해당하는 것만 — 전부 채울 필요 없음)

````markdown
# <모듈 이름>

<한 줄 설명 — 이 모듈이 무엇을 책임지는가>

## Commands

| Command | Description |
|---------|-------------|
| `<install/build/test/lint command>` | <설명> |

## Architecture

```text
<dir>/    # <역할>
<dir>/    # <역할>
```

## Key Files

- `<path>` - <역할>

## Dependencies

- `<dependency>` - <이 모듈이 의존하는 이유·초기화 순서 등 비직관적 관계>

## Environment

- `<VAR_NAME>` - <용도, 필수 여부>

## Testing

- `<test command>` - <무엇을 검증하는지>

## Gotchas

- <비직관적 패턴·트러블슈팅 히스토리·흔한 실수>
````

## 품질 기준 (생성/갱신 여부 판단)

기존 모듈 CLAUDE.md를 다음 축으로 점검하고, 미달 항목만 보완한다(전면 재작성 금지 — 프로젝트 고유
내용은 보존):

- **명령/워크플로우** — 빌드·테스트·린트 명령이 실제로 존재하고 동작하는가.
- **아키텍처** — 주요 디렉터리·진입점·모듈 간 관계가 설명되는가.
- **게치** — 비직관적 패턴·이슈·워크어라운드가 기록되는가.
- **간결성** — 코드가 이미 말해주는 뻔한 내용(예: "UserService 클래스는 사용자 처리를 담당한다")을
  반복하지 않는가.
- **최신성** — 파일 경로/명령/기술스택 버전이 실제 코드베이스와 일치하는가.
- **실행 가능성** — 예시가 이론이 아니라 그대로 쓸 수 있는가(가짜 경로·미완성 TODO 금지).

## Red flags (발견 시 제거)

- 존재하지 않는 경로/명령 참조 (삭제된 파일, 바뀐 명령)
- 템플릿 자리표시자(`<...>`)가 커스터마이즈 없이 그대로 남음
- 같은 사실이 여러 모듈 CLAUDE.md 또는 인덱스와 다르게(또는 중복) 기록됨 — SSOT 위반
- 다시 반복되지 않을 1회성 수정 이력(예: "커밋 abc123에서 로그인 버그 수정") — 삭제
- 일반적인 개발 조언("테스트를 꼭 작성하세요" 등) — 이 프로젝트만의 지식이 아니면 삭제
