# 주석 규율: Fail-Fast 우선 · CRITICAL TRAP 고정 형식 · 기계 검사

## 배경

`rules/doc-style.md` 는 산문 규율의 SSOT 이고 주석·docstring 도 그 대상이다. 그러나
주석에 대해 그 파일이 가진 것은 "Per artifact" 표의 한 항목뿐이다 — "코드가 말할 수
없는 것만". 그 한 줄은 *무엇을 쓰지 말라* 는 말이고, *쓰기 전에 무엇을 먼저 시도하라*
는 말은 어디에도 없다.

`--lint` 가 가진 여섯 규칙(HIST·SHA·PLAN·FILLER·ENDING·CLAIM)은 전부 마크다운 산문을
겨냥해 만들어졌다. 주석 고유의 실패 — How 를 설명하는 주석, 수정 이력, 라인번호 앵커 —
는 하나도 잡히지 않는다.

도달 시점도 문제다. 이 저장소는 `.claude/rules/shipped/doc-style.md` 가 `@import` 로
규칙을 전 세션에 올리지만, **소비자는 그 경로가 없다**. `rules/` 는 플러그인 캐시에만
있고 SessionStart 훅은 `risk-tiers.md` 만 주입한다. 소비자 쪽에서 규칙은 커밋 게이트가
경고할 때, 즉 이미 쓴 뒤에야 도달한다.

## 결정 요약

| 축 | 결정 |
|---|---|
| 주석 이전 단계 | Fail-Fast 우선 — 코드가 스스로 던지게 바꿀 수 있으면 주석을 쓰지 않는다 |
| 불가할 때 형식 | `CRITICAL TRAP` 3줄 고정(마커 · `Trigger:` · `Symptom:`) |
| 기계 검사 신규 | `ANCHOR` · `META` · `TRAP` 세 코드, 전부 error |
| 한 줄 상한 | 린트하지 않는다. TRAP 박스가 다중 줄의 정당한 자리 |
| 판단 절반 | 새 스킬 `prose-review` — 경로를 인자로 받아 기존 코드도 정리 |
| doc-sync 연결 | 1b 단계에서 내부 호출 |
| 최초 작성 도달 | `inject-risk-tiers.sh` 에 요약 문단 + 파일 포인터 |
| 언어 | 안내는 사용자의 언어로 전달하라는 지시를 함께 주입. 박스 키 셋만 언어 불변 리터럴 |
| 측정 | 새 스킬 invocation 케이스 추가 · 훅 변경으로 `hook_assisted` 4개 재측정(sonnet) |

## A. 규칙 본문

`rules/doc-style.md` 의 "Per artifact" 앞에 새 절을 넣는다. 기존 "Comments and
docstrings" 항목은 이 절을 가리키는 한 줄로 줄인다 — 같은 사실이 두 자리에 있으면 안
된다.

문안(영어, 소비자에게 ship):

```markdown
## A comment is the last resort

Before writing one, try to delete the need for it.

1. **Never explain how.** The code says how. A comment that paraphrases the next line
   ages into a lie the moment that line changes, and a reader who trusts it is worse off
   than one who read the code.
2. **Make the code raise instead.** A constraint a reader could violate is a check, not a
   sentence: an `assert`, a raised error, a validated bound, a type. Prose asks to be
   believed; a failing call cannot be ignored.
3. **When it cannot raise, use the box.** Some traps have no runtime moment to fire at —
   a locale that silently changes an encoding, an ordering nothing observes until it is
   wrong. Those get exactly this shape, and nothing else earns three lines:

   ```
   # CRITICAL TRAP: <what breaks, silently>
   # Trigger: <the condition that reaches it>
   # Symptom: <what a reader sees when it does>
   ```

4. **No history, date, or name.** Git holds all three, and holds them correctly.
5. **A filename, never a line number.** `precommit-runner.sh` survives an edit;
   `precommit-runner.sh:31` is false the next time anyone inserts a line above it.
6. **Nothing self-evident.** A comment restating the identifier it sits on is noise that
   costs the reader a line and teaches them to skim the next one.

Everything that is left is a reason or a constraint, and it fits on one line.

The three box keys are literals the checker parses, so they stay as written in every
project. What follows each key is prose: write it in the language the project's comments
are written in.
```

규칙 5 의 예시가 실제 이 저장소에서 고칠 두 앵커라는 점은 의도적이다 — 규칙이 자기
저장소에서 무엇을 잡았는지 보여준다.

실측되지 않은 수치는 기존 "A number is a measurement or a contract" 절이 이미 담당한다.
새 절은 그 사실을 반복하지 않고, `prose-review` 가 판단 항목으로 둘 다 본다.

## B. 기계 절반 — `scripts/doc_style_check.py`

### B-1. `ANCHOR` (error)

```
파일명처럼 생긴 토큰 + `:` + 숫자
```

정규식은 확장자 화이트리스트를 쓴다. 화이트리스트 없이 `\S+:\d+` 로 잡으면 `12:30`,
`localhost:8000`, YAML 의 `key: 3` 이 전부 걸린다. 숫자 쪽에도 조건이 둘 붙는다 —
앞자리 0 없음, 여섯 자리 이하. 확장자가 맞아도 `src/a.py: 0123456` 은 줄 번호가 아니라
sha 이고, 그 구분을 하는 것이 이 두 조건이다(F 참조).

**마스킹이 이 규칙의 핵심이다.** 기존 `_mask` 는 인라인 코드·링크 타깃·URL 을 모두
지운다. 라인 앵커는 거의 언제나 백틱 안이나 링크 텍스트에 쓰이므로, 기본 마스크를 쓰면
이 규칙은 아무것도 잡지 못한다. `ANCHOR` 는 **인라인 코드를 남기고 URL·링크 타깃만
지운** 라인을 읽는다.

URL 을 지우는 이유: `http://localhost:8000` 은 앵커가 아니다. 링크 타깃을 지우는 이유:
`](src/f.py#L42)` 는 GitHub 앵커이지 산문의 주장이 아니다 — 링크 **텍스트** 쪽에
`f.py:42` 가 있으면 그것은 주장이므로 잡힌다.

펜스 블록은 `markdown_prose` 가 이미 제외하므로 로그·출력 예시는 대상이 아니다.
`skills/performance/SKILL.md` 의 리포트 견본이 여기 해당한다.

`READS_LINK_TARGETS = ("PLAN",)` 를 코드→마스크 모드 매핑으로 승격한다. 세 모드:
`default`(기존) · `links`(PLAN) · `code`(ANCHOR).

### B-2. `META` (error)

주석의 이력·날짜·작성자. 키워드만 잡고 맨 날짜는 잡지 않는다 — 날짜 하나로는 이력인지
계약인지 구분할 수 없고, 그 판정은 `prose-review` 의 몫이다.

```
@author · @since · @date
행 머리의 Author: · Created: · Modified: · Updated: · Last updated: · Revision: · History: · Changelog:
작성자 · 작성일 · 수정일 · 변경이력 · 수정이력
```

행 머리 앵커는 `^\s*` 로 충분하지 않다. `python_prose`·`shell_prose` 는 `#` 를 떼고
`.strip()` 한 본문을 주지만 `markdown_prose` 는 원문 줄을 그대로 준다 — 문서가 개정
메타데이터를 적는 실제 두 모양인 `- Updated:` 와 `**Updated:**`, 그리고 인용 `> Updated:`
는 라벨 앞에 불릿·인용 부호·강조가 붙어 있어 `^\s*` 가 흡수하지 못한다. 그래서 행 머리
정의를 헬퍼 하나(`_strip_head`)로 두고 `TRAP` 의 박스 키와 같은 것을 쓴다. 행 머리가
두 규칙에 서로 다른 뜻이면 한쪽이 조용히 꺼진다.

라벨만으로는 판정하지 않는다. `Created`·`Modified`·`History` 는 평범한 단어라
`Modified: files are re-read from disk.` 같은 정의문이 걸린다. 필드와 정의문을 가르는 것은
**값**이다 — 필드는 날짜·버전·이름을 싣고, 정의문은 절을 싣는다. 소문자 단어 뒤에 단어가
더 오면 필드가 아니다. 이 판정에서는 대소문자 무시를 꺼야 한다. 켜 둔 채로는
`Author: John Doe` 도 절로 읽힌다.

`History:` 는 `HIST` 와 겹치지 않는다 — `HIST` 는 서술 어구를, 이것은 필드 라벨을 잡는다.

### B-3. `TRAP` (error)

`CRITICAL TRAP` 마커가 있는 주석 블록에 `Trigger:` 와 `Symptom:` 이 둘 다 없으면 마커
줄에 위반을 단다.

이 규칙만 **블록 인식**이 필요하다. 현재 `lint_text` 는 라인 독립 루프다. 블록은
`prose_of` 가 주는 줄번호의 연속 구간으로 정의한다 — 번호가 1씩 늘고 빈 줄이 아닌 최대
구간. 빈 줄이 블록을 끊는다.

마커가 없는 다중 줄 주석은 잡지 않는다. 잡으면 이 저장소 주석 상당수가 위반이 되고,
그 주석들은 "왜 이렇게 썼는가 + 안 그러면 무엇이 조용히 깨지는가" 라서 잘라내면 사실이
사라진다. 규칙은 한 줄을 기본값으로 말하고, 린트는 박스를 **쓴 경우의 형식**만 강제한다.

## C. 판단 절반 — `skills/prose-review/`

기계가 판정할 수 없는 것: How 설명인지, redundant 인지, Fail-Fast 로 바꿀 수 있는지,
개조식인지, 수치가 실측인지.

```yaml
name: prose-review
description: Use when comments, docstrings or documents need checking against the prose
             rules — before writing them, or to clean up what is already there. Takes
             paths; with none, reads the changed files. doc-sync calls it.
argument-hint: "[paths… | empty = changed files]"
```

스킬 본문은 영어다(저장소 규약). 이 스킬이 사용자에게 내놓는 **위반 보고와 수정안**은
사용자의 언어로 쓴다 — 주입 문안과 같은 이유이고, 같은 지시를 스킬 본문이 한 줄로 담는다.

`allowed-tools` 는 비운다. 이 스킬이 부르는 명령은 전부 경로 인자를 받고, 경로 인자를
사전 승인하려면 규칙이 `*` 로 끝나야 하며, 끝의 `*` 는 접두 일치라 `… && <무엇이든>`
까지 승인된다. `doc-sync` 가 `--derive-id`·`--neighbors` 를 같은 이유로 빼고 있다.

절차:

1. `doc_style_check.py --lint <paths>` — 기계 절반. 이 스크립트가 없는 저장소는 이
   단계를 건너뛰고 판단만 한다(`doc-sync` 1b 와 같은 규약).
2. 판단 절반 — 파일마다 위 다섯 항목.
3. 위반별 수정안. Fail-Fast 로 바꿀 수 있는 것은 주석 삭제 + 검사 추가를 제안한다.
4. 승인 후 적용.
5. `--verify-git <paths>` — 재작성이 무엇도 잃지 않았음을 증명. 산문을 고치는 스킬이
   무손실 증명 없이 끝나면 안 된다.

### doc-sync 연결

`doc-sync` 1b("Prove the rewrite lost nothing") 끝, 게이트 마커 직전에 호출한다. 1b 가
이미 `doc_style_check.py` 를 부르는 자리이고, 마커 이전이어야 통과가 고정점이 된다.

## D. 최초 작성 도달 — `hooks/inject-risk-tiers.sh`

요약 문단만 덧붙인다. 전문을 올리면 매 세션 상시 토큰을 무는데, 주입의 목적은 규칙을
읽히는 것이 아니라 **규칙이 있다는 사실과 어디를 볼지**를 쓰기 전에 도달시키는 것이다.

**문안을 영어로 고정하지 않는다.** 훅은 사용자의 언어를 알 수 없다 — SessionStart 에
전달되는 것 중 그것을 말해 주는 값이 없다. 그러므로 주입 블록은 안내문을 완성된 문장으로
박아 넣는 대신, 그 안내를 **사용자의 언어로 전달하라는 지시**와 함께 넣는다. 언어 판정은
사용자의 입력을 보고 있는 모델만 할 수 있다.

```
The rule below is guidance you apply while writing. Restate it to the user in the
user's language whenever you surface it; never quote it back in English by default.

Before writing a comment, ask whether the code can raise instead — an assert, a
validated bound, a type. If it can, write that and no comment. Only a trap with no
runtime moment to fire at earns the box. Never a how-explanation, a revision history,
a date, an author, or a line number; filenames are fine.

The box keys are literals the linter parses and do not translate:
  CRITICAL TRAP: / Trigger: / Symptom:
Full rule: <plugin root>/rules/doc-style.md
```

**박스 키는 번역하지 않는다.** `CRITICAL TRAP:` · `Trigger:` · `Symptom:` 은 산문이
아니라 `TRAP` 린트가 읽는 리터럴이다. 키를 지역화하면 각 언어의 별칭을 린트가 알아야
하고, 별칭 하나가 빠진 언어는 규칙이 조용히 꺼진 언어가 된다. 키는 고정하고, **키 뒤의
내용은 그 저장소가 쓰는 언어**로 쓴다.

경로는 훅이 이미 가진 `${PLUGIN_ROOT}` 로 채운다 — `risk-tiers.md` 를 읽는 데 쓰는 바로
그 변수다. 문안은 훅 안의 리터럴로 둔다. 파일에서 잘라 읽으면 규칙 파일의 편집이 주입
내용을 조용히 바꾸고, 그 바뀜이 `hook_assisted` 지문에 잡히지 않는다.

FAIL-OPEN 은 훅의 기존 성질이 그대로 간다.

## E. 테스트

| 파일 | 무엇 |
|---|---|
| `tests/doc_style/test_prose_rules.py` | 세 코드의 적중·비적중. `ANCHOR` 는 백틱 안 적중 / URL·링크타깃 비적중이 핵심 |
| `tests/doc_style/test_prose_rules.py` | `TRAP` 블록 경계 — 빈 줄로 끊긴 `Trigger:` 는 같은 블록이 아니다 |
| `tests/skills/` | 새 스킬 프론트매터·링크·참조 |

## F. 이 저장소 정리

CI 린트 대상 245개 파일에서 `ANCHOR` 가 잡는 것은 네 자리다. 셋은 진짜 위반이고 —
`scripts/check-merge-ruleset.sh` 의 두 앵커, 그리고 그 주석 문자열을 그대로 단언하던
`tests/merge_ruleset/test_decoding.py`, 같은 모양을 쓰던
`tests/skills/test_playwright_scaffold.py` — 파일명만 남기고 지운다. 넷째는 오탐이다:
`scripts/wiki_graph.py` 의 YAML 1.1 함정 설명이 `src/a.py: 0123456` 을 예로 드는데,
이것은 경로 키에 sha 같은 값을 둔 매핑이지 줄 참조가 아니다.

그래서 `ANCHOR` 는 숫자 쪽에 두 조건을 더 건다 — **앞자리 0 없음**, **여섯 자리 이하**.
둘 다 줄 번호라는 것의 성질이지 예외 규정이 아니다. 그 파일을 고치는 쪽을 택하지 않은
이유는 따로 있다: `wiki_graph.py` 는 `wiki-init` outcome 평가의 `copy_from_repo` 소스라,
한 바이트만 바뀌어도 실측 재측정이 강제된다. 틀린 규칙을 만족시키려고 그 값을 치를 수는
없다.

`git ls-files` 의 pathspec 에서 `*` 는 디렉터리 구분자를 건너뛴다. `tests/*.py` 는
최상위 테스트가 아니라 `tests/` 아래 전부를 뜻한다.

`META` 는 현재 0건이다.

## G. 측정 비용

- 새 스킬 하나 → `evals/cases.yaml` 에 invocation 케이스 추가, 1회 측정.
- 훅 변경 → `hook_assisted` 를 선언한 4개 스킬의 `description_sha` 가 바뀐다. 재측정
  필요. 핀은 sonnet.

## H. 위험

**`Updated:` 오탐.** 소비자 문서에 필드 라벨로 흔할 수 있다. 규칙이 금지하는 것이
맞으므로 의도한 동작이지만, 소비자가 처음 켤 때 다수 위반을 볼 수 있다. `doc-style`
게이트는 커밋에서 경고만 하고 판정은 CI 가 쥐므로 커밋이 막히지는 않는다.

**`ANCHOR` 가 인라인 코드를 읽는 유일한 규칙이 된다.** 마스크 모드가 셋으로 늘어난다는
뜻이고, 새 규칙을 추가하는 사람이 어느 모드를 쓸지 골라야 한다. 모드 매핑을 한 곳에
두고 기본값을 `default` 로 둔다.
