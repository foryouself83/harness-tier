---
name: harness-authoring
description: "프레임워크에 맞는 AI 하네스(.md 컴포넌트)를 생성하는 작성 규율과 템플릿. /harness-init 가 호출. 3종(skill/agent/rule)+CLAUDE.md+기술문서(분류별 폴더) 골격을 references 의 작성법·필수룰로 채운다. 커맨드는 생성하지 않는다."
---

# harness-authoring

`/harness-init` 의 생성 엔진. `templates/`(골격)을 `references/`(작성법·필수룰)와
research 결과로 채워 호스트 하네스를 만든다.

## 원칙
- **간결·lean** — 생성 .md 는 짧게. 사실은 SSOT 한 곳, 나머지는 링크.
- **필수 룰 5종 항상 주입** — `references/karpathy-principles.md`·`rule-dry-constants.md`·
  `rule-version-pinning.md`·`security-rule.md`·`rule-reuse-first.md` 를 CLAUDE.md `harness:baseline`
  블록에 넣는다. 각 룰의 앵커(`<!-- rule:<key> -->`)를 보존한다(로드경로 보장 — `.claude/rules/` 단독 배치 금지).
- **작성 품질** — `references/skill-writing-guide.md`(pushy desc·Why-first·일반화)·`agent-design-guide.md`
  (분리·재사용·팀 프로토콜)·`tech-doc-guide.md`(기술문서) 를 로드해 따른다. 공식 frontmatter 는
  `references/authoring-spec.md`(공식문서 SSOT) 준수.
- **SSOT 분리** — 구조적 컨벤션은 룰(`<framework>-conventions.md`), 행위적 스타일·BP·안티패턴은
  문서(`docs/code-style/<stack>.md`). 같은 사실을 두 곳에 중복하지 않는다.
- **라이브러리 단정 금지** — 산출물(스킬·에이전트·문서)은 특정 라이브러리/도구를 research·
  code-analyzer 근거 없이 박지 않는다. greenfield 면 카테고리로 일반화하거나 질문(reuse 후보는
  `docs/code-style/<stack>.md` reuse 절). 예: "Zod 스키마" → "프로젝트 검증 라이브러리(없으면 후보 중 택1)".
- **커맨드 미생성** — 어떤 산출물도 `.claude/commands/` 에 만들지 않는다.
- **중복 생성 금지** — detect 의 name+description 으로 기능 중복 시 스킵/질문.
- **vdev 감지 시** 프로세스 규율은 risk-tiers 로 defer, 하네스는 코드스타일+컨벤션만.

## 산출물
- `CLAUDE.md`(baseline 마커블록 + 프레임워크 컨벤션 요약) · 룰(baseline 5종 +
  `<framework>-conventions.md` — 그 안에 `<!-- ops-conventions -->` 앵커 절로 운영 directive 1~3줄씩,
  살은 docs/code-style 링크. **새 마커블록 만들지 않는다**)
- 필요 시 skill / agent (작성가이드 강제, 보조폴더 references/examples 동반) — **command 제외**
- 기술문서(분류별 폴더, `tech-doc-guide.md` 규율):
  `docs/README.md` · `docs/srs/README.md`(greenfield) · `docs/sds/README.md`(Mermaid) ·
  `docs/code-style/README.md` + `docs/code-style/<stack>.md` · `docs/research/`(편입) · `docs/onboarding/README.md` ·
  `docs/performance.md`(확정 스택별 성능 SSOT — 스택 절 + 공통 API 부하 절, 빈 스택 절 금지) ·
  `docs/integration.md`(확정 스택별 통합 검증 SSOT — 스택 절 + 공통 E2E 절, 빈 스택 절 금지) ·
  `docs/operations/commit-versioning-guide.md`(Conventional Commits + SemVer + 감지 스택 릴리스 도구 설정·0.x 정책 — vdev 감지 여부 무관 항상 생성; 작성 지침: `references/commit-versioning-guide.md`)

## 생성 절차
1. detect 결과 + research 결과(`.harness/research/*.md`) + 사용자 선택을 받는다.
2. 산출물별로 해당 `templates/*.template.md` 를 복제하고 플레이스홀더를 채운다(커맨드 템플릿 없음).
3. 필수 룰 5블록을 `references/` 에서 읽어 CLAUDE.md 블록에 합친다(앵커 보존). marker_upsert
   content 에는 `harness:baseline` BEGIN/END 줄을 **넣지 않는다** — body 만(apply 가 래핑).
4. 기술문서를 `tech-doc-guide.md` 의 폴더 구조·작성 순서(SRS→research편입→SDS→code-style
   →onboarding→docs/README)대로 채운다. 출처 링크 의무, 추측 금지. SRS 는 greenfield 만.
   스킬을 생성하면 보조폴더(references/examples)를 `skill-writing-guide.md` 규율대로 동반한다.
   `commit-versioning-guide` 는 `references/commit-versioning-guide.md` 지침으로 `docs/operations/`
   에 생성한다(harness-rules 13-1·13-2 — vdev 감지 여부 무관, 티어/커밋 규율은 risk-tiers defer).
5. **운영 directive/표준 분리(9-3·9-4)**: research 운영 축 섹션을 받아, 룰
   `<framework>-conventions.md` 에 `<!-- ops-conventions -->` 앵커를 두고 그 아래 축별 directive 를
   **항목당 ≤ 3줄**(카테고리 지시 + `docs/code-style/<stack>.md#<axis>` 링크)로 쓴다. 구체 표준명·
   상세·출처·대안은 룰이 아니라 docs/code-style 운영 관심사 섹션에. greenfield 는 룰엔 카테고리만.
6. `plan`(files[]) 으로 모아 `harness_scaffold.py validate` 로 검증한 뒤 `apply` 에 넘긴다(미리보기 후).
