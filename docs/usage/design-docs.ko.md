# 설계 산출물

[English](design-docs.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

사용자가 직접 부르는 여섯 스킬이 요구사항·설계 문서를 `.docx` 산출물로 만듦:
`/design-srs`, `/design-sds`, `/design-architecture`, `/design-api`, `/design-erd`,
`/design-table`. `/flow-init` 을 먼저 실행 — 템플릿을 시딩함.

## 순서

`/design-srs` → `/design-sds` → `/design-architecture` → `/design-erd` → `/design-table` →
`/design-api`. 뒤 문서가 앞 문서의 발급 ID를 참조함; 순서를 어기면 해당 교차 검증이
건너뛰어지고 어느 문서가 없는지 알려줌.

## 각 스킬이 쓰는 것

| 스킬 | 원천 | 결과 |
|---|---|---|
| `/design-srs`, `/design-sds` | `docs/srs/`, `docs/sds/` 원문 그대로 | `.docx` 만 |
| `/design-architecture` | SRS, SDS, 코드 | `<docs>/architecture.md` + `.docx` |
| `/design-api` | SRS, SDS, 아키텍처, 코드 | `<docs>/api.md` + `.docx` |
| `/design-erd` | SRS, SDS, 코드 | `<docs>/erd.md` + `.docx` |
| `/design-table` | SRS, SDS, ERD, 코드 | `<docs>/table.md` + `.docx` |

경로는 `flow-config.yaml` 의 `design_docs` 에서 옴; `gitignore_output: true` 로 두면
`/flow-init` 이 `output` 을 `.gitignore` 에 추가함.

## 템플릿 바꾸기

`design_docs.templates` 아래 파일을 편집. 헤딩·표 헤더 행·`<!-- repeat: PREFIX -->`
블록이 검사 기준이자 `.docx` 구조를 정함; front matter의 `id_prefix`·`refs` 가 ID 규칙.
front matter의 `labels` 키는 `.docx` 의 고정 섹션 — 개정 이력, 목차 — 이름을 다른
언어용으로 바꿈; 제공 템플릿은 한국어 라벨을 씀. 편집 후 검사:

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --templates
```

`/flow-init` 은 이미 있는 템플릿을 절대 덮어쓰지 않음. 파일을 지우면 다음 실행에서
제공 버전으로 되돌아옴.

## 도식은 호스트를 벗어남

` ```mermaid ` · ` ```d2 ` 블록은 `design_docs.renderer`(기본값 `https://kroki.io`)로
전송되고 SVG로 돌아와 `.docx` 에 삽입됨 — Word 2016 이상이면 그대로 보이고, 이전
버전에서는 대체 이미지가 보임. 도식 내용을 네트워크 안에 두려면 자체 호스팅 Kroki를
가리키게 함.

## 의존성

`python-docx`·`markdown-it-py`. 스킬이 부재를 발견하면 설치 전에 물음.
