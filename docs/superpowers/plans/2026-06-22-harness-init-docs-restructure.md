# harness-init 산출물 구조·검증·정리 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/harness-init` 산출 문서를 분류별 폴더+인덱스로 재구조화하고, PRD·Mermaid·스택별 code-style·설정 리서치·툴체인 세트 검증·편입 사본 정리를 추가한다.

**Architecture:** 산출물 골격은 `skills/harness-authoring/templates/`(템플릿), 작성 규율은 `references/`, 오케스트레이션은 `skills/harness-init/SKILL.md`, 결정적 로직은 `scripts/harness_scaffold.py`에 있다. 코드 변경(`cleanup` 서브커맨드)만 TDD로, 문서/규율 변경은 pytest 회귀(기존 테스트 불변)+일관성 점검으로 검증한다.

**Tech Stack:** Python 3(`uv` 실행) · PyYAML · pytest · ruff · pre-commit(gitlint) · Markdown 템플릿.

## Global Constraints

- **커맨드 미생성** — 어떤 산출물도 `.claude/commands/`에 만들지 않는다.
- **덮어쓰기 금지** — 마커블록 upsert / 부재 시 create만. 미리보기·확정 전 쓰기 금지.
- **검증은 진단(FAIL-OPEN), 게이트 아님** — high 이슈도 차단하지 않고 노출만. 지어내지 않음, 모호하면 질문(Karpathy).
- **이중 경로** — `${CLAUDE_PLUGIN_ROOT}`=읽기, `${CLAUDE_PROJECT_DIR}`=쓰기. 플러그인 디렉터리에 쓰지 않는다.
- **필수 룰 5종 baseline 주입** — 앵커 `<!-- rule:<key> -->` 보존, marker content에 BEGIN/END 미포함.
- **Windows 인코딩** — 훅/스크립트 Python은 `force_utf8_io()`·`encoding="utf-8"` 유지(cp949 FAIL-OPEN 방지).
- **flow 감지 시** 프로세스/커밋/머지/PR 규율은 `rules/risk-tiers.md`로 defer.
- **PRD는 greenfield 전용** — brownfield는 PRD 생성 안 함.
- **도구 단정 금지** — 산출물에 특정 도구/라이브러리를 detect/research 근거 없이 박지 않는다. 공식 스캐폴더는 "감지된 프레임워크의 것"으로 일반화.
- **커밋 메시지** — gitlint 준수: 제목 ≤50자, 제목 다음 빈 줄, body 필수(≤80자/줄). conventional commits 한글.

---

### Task 1: `cleanup` 서브커맨드 (TDD)

apply 후 `.harness/`에서 docs로 편입 완료된 중간 사본(`research/`)을 제거하되, 감사용 증거 메타파일(`plan.json`·`manifest.json`·`critic-report.json`·`rationale.md`)은 보존한다.

**Files:**
- Modify: `scripts/harness_scaffold.py` (상수 추가 + `cleanup_harness()` 함수 + `cleanup` 서브파서)
- Test: `tests/test_harness_scaffold.py` (cleanup 테스트 추가)

**Interfaces:**
- Produces: `CLEANUP_PRESERVE: tuple[str, ...]` · `cleanup_harness(harness_dir: Path, root: Path | None = None) -> dict`(반환 `{"removed": list[str], "preserved": list[str], "link_warnings": list[str]}`) · CLI `cleanup --root <path>` (HARNESS_DIR = `<root>/.claude/vway-kit/.harness`, root 로 docs 링크 가드 스캔).

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_harness_scaffold.py` 에 추가(이 파일은 `import scripts.harness_scaffold as hs` 모듈 import 패턴이므로 `hs.` 접두로 호출한다):

```python
def test_cleanup_removes_research_copies_but_preserves_evidence(tmp_path):
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    research = harness / "research"
    research.mkdir(parents=True)
    (research / "researcher_nextjs.md").write_text("조사 내용", encoding="utf-8")
    (research / "code-analyzer.md").write_text("스캔 내용", encoding="utf-8")
    # 보존돼야 하는 감사용 증거
    for name in ("plan.json", "manifest.json", "critic-report.json", "rationale.md"):
        (harness / name).write_text("{}", encoding="utf-8")

    report = hs.cleanup_harness(harness, tmp_path)

    # research 사본은 제거(docs가 .harness를 참조하지 않으므로)
    assert not research.exists() or not any(research.iterdir())
    assert any("researcher_nextjs.md" in r for r in report["removed"])
    assert report["link_warnings"] == []
    # 증거 메타는 보존
    for name in ("plan.json", "manifest.json", "critic-report.json", "rationale.md"):
        assert (harness / name).exists()
    assert sorted(report["preserved"]) == sorted(
        ["critic-report.json", "manifest.json", "plan.json", "rationale.md"]
    )


def test_cleanup_is_safe_when_no_research_dir(tmp_path):
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    harness.mkdir(parents=True)
    (harness / "plan.json").write_text("{}", encoding="utf-8")
    report = hs.cleanup_harness(harness, tmp_path)
    assert report["removed"] == []
    assert report["preserved"] == ["plan.json"]


def test_cleanup_does_not_touch_non_research_non_preserve(tmp_path):
    # 보존 화이트리스트도 아니고 research/ 도 아닌 파일은 건드리지 않는다(보수적).
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    harness.mkdir(parents=True)
    (harness / "stray.txt").write_text("x", encoding="utf-8")
    hs.cleanup_harness(harness, tmp_path)
    assert (harness / "stray.txt").exists()


def test_cleanup_holds_when_docs_link_into_harness(tmp_path):
    # 링크 가드(FAIL-SAFE): docs가 .harness/research 를 참조하면 제거를 보류한다.
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    research = harness / "research"
    research.mkdir(parents=True)
    (research / "researcher_nextjs.md").write_text("조사", encoding="utf-8")
    arch = tmp_path / "docs" / "architecture"
    arch.mkdir(parents=True)
    (arch / "README.md").write_text(
        "출처: [조사](../../.claude/vway-kit/.harness/research/researcher_nextjs.md)",
        encoding="utf-8",
    )
    report = hs.cleanup_harness(harness, tmp_path)
    assert (research / "researcher_nextjs.md").exists()  # 보류로 보존
    assert report["removed"] == []
    assert any("architecture/README.md" in w for w in report["link_warnings"])
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -k cleanup -v`
Expected: FAIL — `AttributeError: module 'scripts.harness_scaffold' has no attribute 'cleanup_harness'`.

- [ ] **Step 3: 구현 추가**

`scripts/harness_scaffold.py` 의 `apply_plan` 함수 **뒤**에 추가:

```python
# 편입 완료된 중간 사본을 정리할 때 절대 지우지 않는 감사용 증거(호스트로 복사되지 않음).
CLEANUP_PRESERVE = ("plan.json", "manifest.json", "critic-report.json", "rationale.md")


def cleanup_harness(harness_dir: Path, root: Path | None = None) -> dict:
    """apply 후 docs로 편입된 중간 사본(research/)을 제거한다.

    링크 가드(FAIL-SAFE): root가 주어지면 docs/ 의 .md 를 스캔해 ".harness/research" 를
    참조하는 링크가 있으면 제거를 보류하고 link_warnings 에 기록한다(편입 누락으로 링크가
    깨질 상황 방지). 감사/재실행용 증거(CLEANUP_PRESERVE)는 항상 보존하고, research/ 와 보존
    목록 외의 파일은 보수적으로 건드리지 않는다.
    """
    report: dict = {"removed": [], "preserved": [], "link_warnings": []}
    research_dir = harness_dir / "research"

    if root is not None:
        docs_dir = root / "docs"
        if docs_dir.is_dir():
            for md in sorted(docs_dir.rglob("*.md")):
                try:
                    text = md.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if ".harness/research" in text:
                    report["link_warnings"].append(
                        str(md.relative_to(root)).replace("\\", "/")
                    )

    if research_dir.is_dir() and not report["link_warnings"]:
        for f in sorted(research_dir.rglob("*"), reverse=True):
            try:
                if f.is_file():
                    f.unlink()
                    report["removed"].append(
                        str(f.relative_to(harness_dir)).replace("\\", "/")
                    )
                elif f.is_dir():
                    f.rmdir()
            except OSError:
                pass  # FAIL-OPEN: 정리는 부가작업, 실패해도 흐름을 막지 않는다
        try:
            research_dir.rmdir()
        except OSError:
            pass

    report["preserved"] = [n for n in CLEANUP_PRESERVE if (harness_dir / n).exists()]
    return report
```

`main()` 의 서브파서 등록부(`v = sub.add_parser("validate")` 블록 뒤)에 추가:

```python
    c = sub.add_parser("cleanup")
    c.add_argument("--root", default=".")
```

`main()` 의 디스패치부(`if args.cmd == "validate":` 블록 뒤, `return 1` 앞)에 추가:

```python
    if args.cmd == "cleanup":
        harness_dir = root / ".claude" / "vway-kit" / ".harness"
        print(json.dumps(cleanup_harness(harness_dir, root), ensure_ascii=False, indent=2))
        return 0
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -k cleanup -v`
Expected: PASS (4 passed).

- [ ] **Step 5: 회귀 + 린트**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: 전체 PASS(기존 테스트 불변).

- [ ] **Step 6: 커밋**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "$(cat <<'EOF'
feat(harness): scaffold cleanup 서브커맨드 추가

apply 후 편입된 research 사본 제거, 증거 메타파일은 보존.
EOF
)"
```

---

### Task 2: 문서 템플릿 재구조화

분류별 폴더 산출을 위한 템플릿을 정비한다. PRD·docs/README 신규, architecture(Mermaid)·code-style(스택별·스니펫 제외·설정 절)·onboarding(문서 링크 허브) 수정.

**Files:**
- Create: `skills/harness-authoring/templates/prd.template.md`
- Create: `skills/harness-authoring/templates/docs-readme.template.md`
- Modify: `skills/harness-authoring/templates/architecture.template.md`
- Modify: `skills/harness-authoring/templates/code-style.template.md`
- Modify: `skills/harness-authoring/templates/onboarding.template.md`
- Modify: `skills/harness-authoring/templates/skill.template.md`

**Interfaces:**
- Produces: 새 플레이스홀더 슬롯(`{{PRODUCT_PURPOSE}}`, `{{MERMAID_DIAGRAM}}`, `{{STACK_LABEL}}`, `{{TOOLCHAIN_CONFIG}}`, `{{KEY_DOC_LINKS}}` 등). Task 3의 authoring 규율과 Task 5의 init 산출 구조가 이 파일명/슬롯을 참조한다.

- [ ] **Step 1: PRD 템플릿 생성** — `templates/prd.template.md`

```markdown
# {{PROJECT_NAME}} 제품 요구사항 (PRD)

> greenfield 전용 — 무엇을·왜 만드는가의 SSOT. 가장 먼저 작성한다. 출처: {{SOURCES}}

## 1. 개요 / 목적
{{PRODUCT_PURPOSE}}

## 2. 목표 / 비목표
- 목표: {{GOALS}}
- 비목표(YAGNI): {{NON_GOALS}}

## 3. 사용자 / 시나리오
{{USERS_AND_SCENARIOS}}

## 4. 기능 요구사항
{{FUNCTIONAL_REQUIREMENTS}}  <!-- 요구사항별 ID·설명·우선순위. 모호하면 "확인 필요". -->

## 5. 비기능 요구사항
{{NON_FUNCTIONAL_REQUIREMENTS}}  <!-- 성능·보안·가용성·확장성·접근성 등. -->

## 6. 제약 / 가정
{{CONSTRAINTS_ASSUMPTIONS}}

## 7. 성공 지표 (KPI)
{{SUCCESS_METRICS}}
```

- [ ] **Step 2: docs/README 인덱스 템플릿 생성** — `templates/docs-readme.template.md`

```markdown
# {{PROJECT_NAME}} 문서

프로젝트 문서 전체 구조. 처음이라면 [온보딩](onboarding/README.md)부터 본다.

## 구조
{{PRD_INDEX_LINE_IF_GREENFIELD}}
- [아키텍처](architecture/README.md) — 구조 + Mermaid 다이어그램
- [코드 스타일](code-style/README.md) — 스택별 컨벤션·BP·안티패턴·툴체인 설정
- [리서치](research/README.md) — 프레임워크 컨벤션·설정·기성 솔루션 조사
- [온보딩](onboarding/README.md) — 실행·디버그·문서 안내

<!-- 출처: {{SOURCES}} -->
```

- [ ] **Step 3: architecture 템플릿 수정** — `templates/architecture.template.md` 전체를 아래로 교체

```markdown
# {{PROJECT_NAME}} 아키텍처

## 스택 / 프레임워크
{{FRAMEWORK}} {{VERSION}} — {{STACK_SUMMARY}}  <!-- 출처: {{SOURCES}} -->

## 구조 다이어그램
```mermaid
{{MERMAID_DIAGRAM}}
```
<!-- 컴포넌트/모듈 관계(최소 1개). 확인된 사실만 노드화(추측 노드 금지). 가능하면 데이터 흐름도 추가. -->

## 폴더 구조
{{FOLDER_MAP}}

## 주요 모듈 / 데이터 흐름
{{MODULES_AND_FLOW}}
```

- [ ] **Step 4: code-style 템플릿 수정** — `templates/code-style.template.md` 전체를 아래로 교체(스택별 `<stack>.md` 골격, 코드 스니펫 제외, 툴체인 설정 절 추가)

```markdown
# {{STACK_LABEL}} 코드 스타일

> {{LANGUAGE}} + {{FRAMEWORK_OR_PLATFORM}}. **코드 스니펫 없이** 규율을 산문으로 서술한다. 출처: {{SOURCES}}

## 네이밍 · 포맷 · 임포트
{{STYLE_RULES}}

## 베스트 프랙티스
{{BEST_PRACTICES}}  <!-- 이 스택 특유의 권장 패턴. 각 1-2줄 + 출처. -->

## 안티패턴 (피한다)
{{ANTI_PATTERNS}}
- **바퀴 재발명**: 무료·상용가능 기성 솔루션(공식 이미지·표준 라이브러리·OSS)이 있으면 직접 구현 대신 사용.

## 툴체인 / 설정
{{TOOLCHAIN_CONFIG}}  <!-- 빌드·번들·타입체크·린트·테스트를 한 세트로. 감지된 버전의 공식 스캐폴더 출력 기준. 출처 표기. -->

## reuse 후보 (무료·상용가능)
{{REUSE_EXAMPLES}}
```

- [ ] **Step 5: onboarding 템플릿 수정** — `templates/onboarding.template.md` 전체를 아래로 교체(문서 링크 허브 추가)

```markdown
# {{PROJECT_NAME}} 온보딩

## 실행
{{RUN_COMMANDS}}

## 브랜치 / 워크플로
{{BRANCH_FLOW}}

## 디버그
{{DEBUG_NOTES}}

## 주요 문서 (처음이라면 이 순서로)
{{KEY_DOC_LINKS}}  <!-- PRD→architecture→code-style→research 링크. greenfield 아니면 PRD 생략. -->
```

- [ ] **Step 6: skill 템플릿 수정** — `templates/skill.template.md` 끝에 보조폴더 안내 주석 추가(기존 본문 유지)

기존 파일 끝(`{{PROCEDURE}}` 다음 줄)에 추가:

```markdown

<!-- 보조 자료(역할상 참조/사례가 있을 때만 — YAGNI, 단순 스킬엔 강제 금지):
     references/<topic>.md  — 상세 참조(progressive disclosure; 본문은 포인터만 두고 상세는 여기)
     examples/<case>.md     — 입력/출력 사례를 최소 1개. 긴 설명보다 예시 하나가 낫다. -->
```

- [ ] **Step 7: 회귀 확인**

Run: `uv run pytest`
Expected: PASS(템플릿은 코드가 아니므로 기존 테스트 불변).

- [ ] **Step 8: 커밋**

```bash
git add skills/harness-authoring/templates/
git commit -m "$(cat <<'EOF'
feat(harness): 산출 문서 템플릿 분류별 재구조화

PRD·docs README 신규, architecture Mermaid·스택별 code-style·온보딩 링크 허브.
EOF
)"
```

---

### Task 3: authoring 규율 + 작성 가이드

템플릿을 어떻게 채우는지의 규율을 갱신한다: 폴더 구조·작성 순서·스택 분리·Mermaid·출처·스킬 보조폴더·`version-compat` 검토.

**Files:**
- Modify: `skills/harness-authoring/SKILL.md` (산출물·절차)
- Modify: `skills/harness-authoring/references/tech-doc-guide.md` (문서 구조 규율)
- Modify: `skills/harness-authoring/references/skill-writing-guide.md` (references/examples 동반)
- Modify: `skills/harness-authoring/references/critique-guide.md` (`version-compat` 항목)

**Interfaces:**
- Consumes: Task 2의 템플릿 파일명/슬롯.
- Produces: critic 출력 `kind` enum 확장값 `version-compat`(Task 4의 critic이 사용).

- [ ] **Step 1: tech-doc-guide 재작성** — `references/tech-doc-guide.md` 전체를 아래로 교체

````markdown
# 기술문서 작성 가이드

`harness-authoring` 이 호스트 프로젝트용 기술문서를 생성할 때 따르는 규율.

## 폴더 구조 (분류별)

문서는 분류별 폴더에 두고 진입 문서는 `README.md` 로 한다(GitHub 폴더 렌더링 친화적).

```text
docs/
  README.md                  전체 인덱스 · 가장 마지막 작성(다른 문서를 링크)
  prd/README.md              기능/비기능 요구사항 · greenfield 전용 · 가장 먼저 작성
  architecture/README.md     구조 + Mermaid 구조도(필수)
  code-style/
    README.md                스택 인덱스 + 공통 원칙
    <stack>.md               스택별 컨벤션(스니펫 제외)
  research/
    README.md                리서치 요약 인덱스
    <topic>.md               .harness/research/ 에서 편입(출처 링크)
  onboarding/README.md       실행/디버그 + 주요 문서 링크 · 가장 마지막 작성
```

**작성 순서**: `PRD → research편입 → architecture → code-style → onboarding → docs/README`.
research 는 architecture·code-style 의 **입력(근거)이므로 먼저 편입**한다(그래야 두 문서가 이미
편입된 `docs/research/` 를 출처로 링크할 수 있다).
**기존 `docs/` 관례 존중**: 이미 다른 구조(`documentation/` 등)면 그쪽을 우선하고 누락 분류만 추가한다.
**PRD 는 greenfield 전용** — brownfield 에선 PRD 를 만들지 않는다.
**출처 링크 의무** — 모든 문서는 참조한 research 문서/외부 URL 을 마크다운 링크로 단다. 근거 없으면 "출처 미확인".

## SSOT 분리 (중복 금지)

- **구조적 컨벤션**(폴더/스키마 위치) → `.claude/rules/<framework>-conventions.md`(룰).
- **행위적 가이드**(네이밍·포맷·BP·안티패턴·툴체인 설정) → `docs/code-style/<stack>.md`(문서).
- 룰이 문서를 가리키되 내용을 복제하지 않는다.

## PRD (greenfield) — prd/README.md

`prd.template.md` 를 채운다: 목적·목표/비목표·사용자/시나리오·기능 요구사항(ID·우선순위)·
비기능 요구사항(성능·보안·가용성 등)·제약/가정·성공 지표. 인터뷰/research 로 채우고 모르면 "확인 필요".

## ARCHITECTURE — architecture/README.md

스택/버전 + 폴더 구조 + 주요 모듈/데이터 흐름 + **Mermaid 구조도(필수, 최소 1개)**.
확인된 사실만 노드화한다(추측 노드 금지). 가능하면 데이터 흐름 다이어그램을 추가한다.

## code-style — code-style/README.md + <stack>.md

- 스택별로 파일을 나눈다. 파일명 = `<language>` 또는 `<language>-<framework>`(또는 플랫폼).
  예: `typescript-react.md`·`python-fastapi.md`·`go.md`. **같은 언어여도 프레임워크/플랫폼이
  다르면 분리**(강조점이 달라 한 파일로 묶으면 둘 다 얕아진다).
- 각 `<stack>.md` 는 네이밍·포맷·임포트 / 베스트 프랙티스 / 안티패턴(바퀴 재발명 포함) /
  툴체인 설정 / reuse 후보를 **산문으로 상세히** 쓴다. **코드 스니펫은 넣지 않는다**.
- **툴체인 설정은 한 세트로** — 빌드러너·컴파일러·번들러·타입체커·린터·테스트러너의 상호
  정합성(예: `tsc -b`(references) ↔ 번들러 include scope)을 함께 기술한다. 감지된 버전의
  공식 작성법을 출처와 함께.
- `code-style/README.md` 는 스택 목록 링크 + 공통 원칙(출처 표기 등)만 둔다.

## research — research/README.md + <topic>.md

`.harness/research/*.md` 를 사람이 읽을 수 있게 정제(출처 링크 추가)해 `docs/research/` 로 편입한다.
`research/README.md` 는 조사 항목 요약 인덱스. **다른 문서가 research 를 출처로 링크할 때는 편입
위치 `docs/research/` 를 가리킨다 — gitignored 증거인 `.harness/` 경로를 산출물에 절대 넣지 않는다**
(편입 후 `.harness/research/` 사본은 init 의 cleanup 이 정리하므로 `.harness/` 링크는 깨진다).

## onboarding — onboarding/README.md (가장 마지막)

실행/디버그 + **"처음 온 사람을 위한 주요 문서 링크"** 절(PRD·architecture·code-style·research 로의 링크).
flow 감지 시 커밋·PR 규율은 risk-tiers 로 defer(여기 중복 금지). 다른 문서가 다 작성된 뒤 마지막에 쓴다.

## 공통 규율

- **출처 표기** — 리서치/스캔 근거를 단다. 없으면 "출처 미확인".
- **간결** — 항목당 1-2줄. 장황한 설명보다 구체.
- 문서는 사람과 에이전트 양쪽이 읽는다 — 명확하고 스캔 가능하게.
````

- [ ] **Step 2: skill-writing-guide 보강** — `references/skill-writing-guide.md` 의 `## 5. Progressive Disclosure` 절 본문 끝에 추가

기존 `## 5. Progressive Disclosure` 절의 마지막 불릿(`- **300줄 초과 reference 는 상단 목차** 포함.`) 다음에 추가:

```markdown

**보조 폴더 동반** — 스킬 생성 시 역할상 분리할 참조/사례가 있으면 `<skill>/references/`(상세
참조)·`<skill>/examples/`(입력/출력 사례 최소 1개)를 함께 만든다. 본문은 개요+포인터만 두고
상세는 references 로 내린다. **단순 스킬에 강제하지 않는다**(YAGNI) — 참조/사례가 실제로 있을 때만.
```

- [ ] **Step 3: critique-guide에 version-compat 추가** — `references/critique-guide.md` 수정

(a) 출력 형식 코드블록의 `kind` 를 확장: `"kind": "quality|coherence|reuse|command"` → `"kind": "quality|coherence|reuse|command|version-compat"` (코드블록 내 1곳).

(b) `## 4. 커맨드 미생성 (kind: command)` 절 **뒤**에 새 절 추가:

```markdown
## 5. 버전 호환성 (`kind: version-compat`)

툴체인을 **한 세트**로 본다(빌드러너·컴파일러·번들러·타입체커·린터·테스트러너는 맞물려 있다).

- 감지된 **실제 패키지 버전**의 공식 작성법과 산출물(특히 실폴더 스캐폴딩 설정파일)이 일치하는가?
- **툴체인 상호 정합성**: 빌드 스크립트 ↔ 설정이 어긋나지 않는가? (예: `tsc -b`(project references
  모드)인데 루트 tsconfig 에 `references` 가 없음; 루트 `vite.config.ts` 가 어느 tsconfig 프로젝트
  scope 에도 안 잡혀 `include` 밖에 있음.)
- 메이저 버전에 따라 갈리는 설정 스키마/기본값을 잘못 적용하지 않았는가?
- 설정을 손으로 추론해 짜맞췄는가? → 감지된 프레임워크의 **공식 스캐폴더 출력 복제**가 권위 baseline.
```

(c) 기존 `## 5. 드라이런 (판단)` 절 제목을 `## 6. 드라이런 (판단)` 으로 번호 조정.

- [ ] **Step 4: harness-authoring SKILL 갱신** — `skills/harness-authoring/SKILL.md` 의 `## 산출물` 절을 아래로 교체

```markdown
## 산출물
- `CLAUDE.md`(baseline 마커블록 + 프레임워크 컨벤션 요약) · 룰(baseline 5종 + `<framework>-conventions.md`)
- 필요 시 skill / agent (작성가이드 강제, 보조폴더 references/examples 동반) — **command 제외**
- 기술문서(분류별 폴더, `tech-doc-guide.md` 규율):
  `docs/README.md` · `docs/prd/README.md`(greenfield) · `docs/architecture/README.md`(Mermaid) ·
  `docs/code-style/README.md` + `docs/code-style/<stack>.md` · `docs/research/`(편입) · `docs/onboarding/README.md`
```

이어서 `## 생성 절차` 의 4번 항목(`4. 기술문서 3종을 ...`)을 아래로 교체:

```markdown
4. 기술문서를 `tech-doc-guide.md` 의 폴더 구조·작성 순서(PRD→architecture→code-style→research편입
   →onboarding→docs/README)대로 채운다. 출처 링크 의무, 추측 금지. PRD 는 greenfield 만.
   스킬을 생성하면 보조폴더(references/examples)를 `skill-writing-guide.md` 규율대로 동반한다.
```

- [ ] **Step 5: 회귀 + 일관성 점검**

Run: `uv run pytest`
Expected: PASS.
점검: tech-doc-guide의 폴더 구조 ↔ Task 2 템플릿 파일명/슬롯이 일치하는가(육안).

- [ ] **Step 6: 커밋**

```bash
git add skills/harness-authoring/SKILL.md skills/harness-authoring/references/
git commit -m "$(cat <<'EOF'
feat(harness): authoring 규율 문서 구조·version-compat 반영

폴더 구조·작성 순서·스택 분리·스킬 보조폴더·툴체인 세트 검토 규율 갱신.
EOF
)"
```

---

### Task 4: 에이전트 보강 (researcher · critic)

리서치는 설정 방법 수집 + 자율 확장 + 툴체인 세트/권위 출력을, 비판은 `version-compat` 검토 영역을 갖는다.

**Files:**
- Modify: `agents/harness-researcher.md`
- Modify: `agents/harness-critic.md`

**Interfaces:**
- Consumes: Task 3 critique-guide의 `version-compat` 항목.
- Produces: critic `critic-report.json` 의 `kind` 에 `version-compat` 포함.

- [ ] **Step 1: researcher 절차 보강** — `agents/harness-researcher.md` 의 `## 절차` 절 끝(4번 항목 뒤)에 추가

```markdown
5. **설정 방법(config) 버전별 수집**: 빌드/번들러(tsconfig·vite·webpack·tsc 모드)·타입체크·
   린트/포맷·테스트 러너·패키지 매니저·환경/시크릿 관리의 **실제 작성법**을 버전과 함께 모은다.
6. **툴체인은 한 세트로**: 위 도구들의 상호 정합성을 함께 본다(개별 파일 따로 보지 않는다).
   설정 작성법이 불확실하면 **감지된 프레임워크의 공식 스캐폴더가 생성하는 출력**(권위 baseline)을
   확인해 보고한다(도구 이름은 예시일 뿐 단정 금지 — 감지된 프레임워크의 것).
7. **자율 확장**: 프레임워크 특성상 추가로 필요한 설정 항목을 스스로 판단해 조사한다(예: SSR/라우팅·
   ORM 마이그레이션·컨테이너 빌드 등). 무엇을 왜 추가 조사했는지 근거를 남긴다.
```

- [ ] **Step 2: researcher 출력 형식 보강** — `agents/harness-researcher.md` 출력 형식 코드블록의 `### 스키마/설정 컨벤션` 항목을 아래로 교체

```markdown
### 설정/툴체인 (버전별, 한 세트)
- 빌드/번들/타입체크/린트/테스트/패키지매니저 설정 작성법 ... (출처: URL)
- 툴체인 상호 정합성 주의 ... (출처: URL)
- 권위 baseline: <감지된 프레임워크의 공식 스캐폴더> 출력 기준 ... (출처: URL)
### 자율 확장 항목 (프레임워크 특성상 추가 조사)
- <항목> — 왜 필요한지 + 작성법 ... (출처: URL)
```

- [ ] **Step 3: critic 검토 영역 추가** — `agents/harness-critic.md` 의 `## 검토 영역` 절 5번으로 추가(4번 뒤)

```markdown
5. **버전 호환성**(`version-compat`): 툴체인을 한 세트로 보고, 감지된 실제 버전의 공식 작성법과
   산출물(특히 실폴더 스캐폴딩 설정)이 일치하는지, 빌드 스크립트↔설정 정합성(`tsc -b`↔references,
   번들러 설정의 프로젝트 scope 포함 등)을 검토한다. 자세한 기준은 critique-guide 5절.
```

- [ ] **Step 4: critic 출력 enum 갱신** — `agents/harness-critic.md` 의 출력 형식 코드블록 `"kind"` 를 `"quality|coherence|reuse|command"` → `"quality|coherence|reuse|command|version-compat"` 로 교체.

- [ ] **Step 5: 회귀 + 일관성 점검**

Run: `uv run pytest`
Expected: PASS.
점검: critic 출력 `kind` enum(critic 에이전트) ↔ critique-guide 출력 형식 ↔ critique-guide 5절 제목 일치.

- [ ] **Step 6: 커밋**

```bash
git add agents/harness-researcher.md agents/harness-critic.md
git commit -m "$(cat <<'EOF'
feat(harness): 에이전트에 설정 리서치·version-compat 추가

researcher 설정 수집·자율확장·권위 baseline, critic 툴체인 세트 검토.
EOF
)"
```

---

### Task 5: init 오케스트레이션 + 규율 SSOT

전체 흐름을 결선한다: research→docs 편입, cleanup Step, 그리고 모든 규율의 SSOT인 `harness-rules.md` 갱신.

**Files:**
- Modify: `skills/harness-init/SKILL.md`
- Modify: `rules/harness-rules.md`

**Interfaces:**
- Consumes: Task 1 `cleanup` 서브커맨드, Task 2 템플릿, Task 3 authoring 규율, Task 4 에이전트.

- [ ] **Step 1: init Step 4(생성) 갱신** — `skills/harness-init/SKILL.md` 의 `## Step 4 — 생성` 의 1번 하위 항목 중 "기술문서 3종을 ..." 줄을 아래로 교체

```markdown
   - 기술문서를 분류별 폴더로 채운다(PRD greenfield→research 편입→architecture(Mermaid)→스택별
     code-style→onboarding→docs/README 순, 출처 링크). research 는 `.harness/research/` 를 정제해
     `docs/research/` 로 먼저 편입하고(architecture·code-style 의 근거), 이후 문서는 출처를
     `docs/research/` 로 링크한다(`.harness/` 참조 금지). 스킬 생성 시 references/examples 보조폴더 동반.
```

- [ ] **Step 2: init Step 7 뒤에 cleanup Step 추가** — `## Step 7 — apply (scaffold)` 절 **뒤**, `## Step 8 — 보고` **앞**에 삽입

````markdown
## Step 7.5 — cleanup (편입 사본 정리)
apply 성공 후, docs 로 편입된 중간 사본을 정리한다(재실행/업데이트 시 혼란 방지).
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" cleanup --root "${ROOT}"
```
`.harness/research/` 등 편입 사본만 제거하고 증거 메타(`plan.json`·`manifest.json`·
`critic-report.json`·`rationale.md`)는 보존한다(감사/재실행용). **링크 가드**: docs 가
`.harness/research` 를 참조하면 제거를 보류하고 `link_warnings` 로 보고한다(링크 깨짐 방지).
FAIL-OPEN — 정리 실패는 흐름을 막지 않는다. `link_warnings` 가 있으면 보고에 노출한다.
````

- [ ] **Step 3: init Step 8(보고) 갱신** — `## Step 8 — 보고` 절의 첫 문장에 cleanup 결과 추가

기존 "생성/스킵/사용자보류 + 출처 URL + critic 결과 + 후속(스캐너 설치 명령 등)을 **표로** 요약." 를:

```markdown
생성/스킵/사용자보류 + 출처 URL + critic 결과(`version-compat` 포함) + cleanup 결과(제거/보존) +
후속(스캐너 설치 명령 등)을 **표로** 요약.
```

- [ ] **Step 4: harness-rules SSOT 갱신** — `rules/harness-rules.md` 의 `## 산출물` 절 8번 항목을 교체하고 신규 항목 추가

(a) 8번(`8. **기술문서 3종**: ...`)을 아래로 교체:

```markdown
8. **기술문서(분류별 폴더)**: `docs/README.md`(전체 인덱스·마지막) · `docs/prd/`(기능/비기능
   요구사항·greenfield 전용·가장 먼저) · `docs/architecture/`(구조 + **Mermaid 필수**) ·
   `docs/code-style/`(스택별 `<stack>.md`, 코드 스니펫 제외, 툴체인 설정 한 세트) ·
   `docs/research/`(편입, 출처 링크) · `docs/onboarding/`(실행/디버그 + 주요 문서 링크·마지막).
   진입 문서는 `README.md`. 구조적 컨벤션은 룰, 행위적 스타일은 문서 — **한 사실 한 곳**.
   **모든 문서는 참조 출처를 링크로** 단다.
```

(b) `## 다중 에이전트 / 비판` 절의 12번(`12. **경량 비판**: ...`) 뒤에 추가:

```markdown
12-1. **버전 호환성(`version-compat`)**: 툴체인을 한 세트로 보고 감지된 실제 버전의 공식 작성법과
    산출물 정합성을 검증한다(빌드↔설정, 예: `tsc -b`↔references). **만들 때**는 설정을 추론하지 말고
    감지된 프레임워크의 **공식 스캐폴더 출력을 복제**해 baseline 으로 삼는다(reuse-first 의 설정판).
    researcher 는 설정 방법을 버전별로 수집하고 프레임워크 특성상 필요한 항목을 자율 확장한다.
```

(c) `## 안전` 절 끝(4번 뒤)에 cleanup 규율 추가:

```markdown
5. **편입 사본 cleanup**: apply 성공 후 docs 로 편입된 중간 사본(`.harness/research/` 등)은
   `harness_scaffold.py cleanup` 으로 제거한다. 감사용 증거(`plan.json`·`manifest.json`·
   `critic-report.json`·`rationale.md`)는 보존. FAIL-OPEN(정리 실패는 흐름을 막지 않는다).
   **링크 가드(FAIL-SAFE)**: 문서 출처 링크는 편입 위치 `docs/research/` 를 가리키고 `.harness/` 를
   참조하지 않는다. cleanup 은 제거 전 docs 가 `.harness/research` 를 참조하는지 검사해, 참조가
   있으면 제거를 보류하고 경고한다(링크 깨짐 방지).
```

(d) 기존 `## 산출물` 절 5번(`5. **.md 기본**, 실설정(bandit·CI·pre-commit·실폴더·실제 ==핀)은 항목별 opt-in.`) 뒤에 스킬 보조폴더 규율 추가:

```markdown
5-1. **스킬 보조폴더**: 스킬 생성 시 역할상 참조/사례가 있으면 `references/`·`examples/` 를 동반한다(YAGNI — 단순 스킬엔 강제 안 함).
```

- [ ] **Step 5: 전체 회귀 + 정적 분석**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check && uv run pre-commit run --all-files`
Expected: PASS(pre-commit은 변경 .md/.py 대상; gitlint은 커밋 시점).

- [ ] **Step 6: 일관성 최종 점검**

육안 점검 체크리스트:
- init SKILL의 cleanup Step ↔ Task 1 서브커맨드 인자(`cleanup --root`) 일치.
- harness-rules 산출물 8번 ↔ tech-doc-guide 폴더 구조 ↔ Task 2 템플릿 일치.
- `version-compat` 표기가 critic·critique-guide·harness-rules에서 동일.
- PRD greenfield 전용이 SKILL·tech-doc-guide·harness-rules에서 일관.

- [ ] **Step 7: 커밋**

```bash
git add skills/harness-init/SKILL.md rules/harness-rules.md
git commit -m "$(cat <<'EOF'
feat(harness): init 편입·cleanup Step과 규율 SSOT 결선

research→docs 편입·cleanup Step·문서구조·version-compat·cleanup 규율.
EOF
)"
```

---

## Self-Review (작성자 점검 결과)

**1. Spec coverage** — spec 요구사항별 task 매핑:
- A(문서 구조: 폴더화·README·Mermaid·스택 code-style·onboarding 링크·PRD·research편입·출처) → Task 2(템플릿)+Task 3(tech-doc-guide)+Task 5(init/rules).
- B(리서치 설정 수집·자율확장·툴체인 세트·권위출력 / version-compat 검증) → Task 3(critique-guide)+Task 4(researcher/critic)+Task 5(rules).
- C(cleanup) → Task 1(코드)+Task 5(init Step/rules).
- D(스킬 references/examples) → Task 2(skill.template)+Task 3(skill-writing-guide)+Task 5(rules).
- E(tsconfig 버그=B의 사례) → Task 3·4의 version-compat로 커버(템플릿 신설 안 함, 비목표 일치).

**2. Placeholder scan** — "TBD/TODO/적절히 처리" 없음. 문서 task는 실제 최종 텍스트 제공. 코드 task는 완전 코드.

**3. Type/이름 일관성** — `cleanup_harness`·`CLEANUP_PRESERVE`·`cleanup --root` 가 Task 1↔Task 5에서 일치. `version-compat` 문자열이 Task 3·4·5에서 동일. 템플릿 파일명(`prd.template.md`·`docs-readme.template.md` 등)이 Task 2↔Task 3·5 참조에서 일치.

**비목표 준수** — 커맨드 미생성·tsconfig 템플릿 신설 안 함·단순 스킬 보조폴더 비강제·brownfield PRD 미생성.
