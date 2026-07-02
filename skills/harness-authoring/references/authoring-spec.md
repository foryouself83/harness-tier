# 컴포넌트 작성법 (SSOT: 공식문서)

모델 지식이 아니라 공식문서를 SSOT로 확인:
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) ·
[hooks](https://code.claude.com/docs/en/hooks.md) ·
[skills](https://code.claude.com/docs/en/skills.md).

> **커맨드는 작성하지 않는다.** harness 산출물에 `.claude/commands/` 는 포함되지 않는다
> ([harness-rules.md](../../../rules/harness-rules.md) #9). 아래는 생성 대상 컴포넌트뿐이다.

- **agent** (`.claude/agents/<name>.md`): frontmatter `name`·`description`(+호출 예시)
  ·`model`(선택) + 단일 책임 시스템 프롬프트.
- **skill** (`.claude/skills/<name>/SKILL.md`): frontmatter `name`·`description`
  (트리거 신호 포함) + 트리거·절차. Progressive Disclosure(상세는 references/).
- **rule** (`.claude/rules/<name>.md`): frontmatter 는 **선택적 `paths`(glob 리스트)만** —
  `name`/`description` 필드는 쓰지 않는다(룰은 컴포넌트가 아니라 CLAUDE.md 계열 instructions).
  `paths` 없으면 매 세션 자동 로드(`.claude/CLAUDE.md` 우선순위), 있으면 매칭 파일 작업 시 로드.
  템플릿의 `{{PATHS_FRONTMATTER_OR_REMOVE}}` 는 경로 한정 룰이면 `---`/`paths:`/`---` 블록으로,
  전역 룰이면 빈 문자열로 치환한다. **필수 룰 5종은 확실성을 위해 CLAUDE.md baseline 본문에 주입**한다.

**공통 규율**: 간결·lean, 사실은 SSOT 한 곳에만 두고 나머지는 링크.
