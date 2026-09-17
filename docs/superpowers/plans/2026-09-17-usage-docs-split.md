# USAGE 분할 + README/USAGE 현행화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** USAGE 를 `docs/usage/` 주제별 12개 문서(+ko twin)로 나누고, README·USAGE 를 현재 코드와 일치시키며, 소스 결함 4건을 수정함.

**Architecture:** 가드 테스트를 먼저 새 경로로 옮겨 실패시킨 뒤 문서를 채움. 사실 하나는 spec 의 "사실별 원본 위치" 표가 정한 파일에만 두고, 다른 곳은 링크. 모든 서술은 소스 파일을 읽어 확인한 뒤 씀.

**Tech Stack:** Markdown, pytest, `scripts/_md_anchors.py`, `scripts/doc_style_check.py`, WSL ShellCheck.

**Spec:** `docs/superpowers/specs/2026-09-17-usage-docs-split-design.md`

## Global Constraints

- 저장소 문서·주석·테스트 메시지는 영어. `.ko.md` twin 과 `docs/superpowers/` 만 한국어.
- 한국어 문서 종결은 `~다` 금지(doc-style `ENDING`) — 명사형·`~함`·`~임`.
- doc-style 금지 항목: `HIST` · `SHA` · `PLAN` · `FILLER` · `ANCHOR` · `META`. 100자 넘는 prose 줄 지양. inline-code span 은 줄바꿈을 건너지 않음.
- Markdown 은 손으로 줄바꿈 — textwrap 등 기계적 재배치 금지.
- 모든 서술은 해당 소스 파일을 읽고 확인 후 작성. 감사 보고서는 근거가 아님.
- 소비자 계약만: 언제 부르나 · 인자 · 선행조건 · 무엇을 쓰나 · 생략 시 깨지는 것. SKILL.md 절차 재서술 금지.
- 스킬 표기는 `/name`.
- 커밋은 브랜치당 하나(amend), 타입 `fix`, `commit` 스킬로. 게이트: `review.done` · `doc-sync.done` (`.claude/vway-kit/.vdev/`).
- `git switch`/`checkout`/`stash` 금지 — 작업 브랜치 `feature/usage-docs-split` 유지.

## File Structure

| 경로 | 책임 |
|------|------|
| `tests/docs/test_usage_docs.py` (new) | twin 존재, 색인 완결성, 상대 링크·앵커 해석 |
| `tests/docs/test_tier_table_parity.py` | 등급표 사본 경로 → `docs/usage/tiers-and-gates{,.ko}.md` |
| `tests/skills/test_shipped_contracts.py` | 스킬 등록·review_checklist 검사 경로 |
| `docs/usage/*.md` · `*.ko.md` (new, 24) | 주제별 사용 설명 |
| `USAGE.md` · `USAGE.ko.md` | 색인 |
| `README.md` · `README.ko.md` | 개요·설치·제공물 정정 |
| `CLAUDE.md` | `docs/usage/` 반영 |
| `.github/workflows/release.yml` · `flow-config.example.yaml` | USAGE 경로 참조 갱신, `feature_prefix` 삭제 |
| `scripts/check-deps.sh` | superpowers 마켓 안내·등급명 |
| `skills/flow-init/SKILL.md` · `skills/flow-init/references/setup-script-actions.md` | `feature_prefix` 질문 삭제, versioning 렌더 항목 |
| `skills/flow-uninstall/SKILL.md` | `srs-verify.yml` 후속 조치 |

---

### Task 1: 가드 테스트를 새 구조로 이동 (RED)

**Files:**
- Create: `tests/docs/test_usage_docs.py`
- Modify: `tests/docs/test_tier_table_parity.py`, `tests/skills/test_shipped_contracts.py`

**Interfaces:**
- Produces: `USAGE_DIR = REPO / "docs/usage"`; 문서 이름 집합 `TOPICS` (12개, 확장자 제외).

- [ ] **Step 1: `tests/docs/test_usage_docs.py` 작성**

```python
"""The consumer usage guide is one index plus per-topic documents, each with a Korean twin.

A split guide fails in ways no single file shows: a topic written in one language only, an
index that stops naming a topic, a link that still points at a section that moved files.
"""

import re
from pathlib import Path

import pytest

from scripts._md_anchors import _has_anchor, _strip_code

ROOT = Path(__file__).resolve().parents[2]
USAGE_DIR = ROOT / "docs" / "usage"
TOPICS = (
    "getting-started",
    "configuration",
    "tiers-and-gates",
    "daily-work",
    "promotion-and-release",
    "deployments",
    "ci-workflows",
    "project-harness",
    "manual-verification",
    "teams",
    "troubleshooting",
    "update-and-removal",
)
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _en(topic: str) -> Path:
    return USAGE_DIR / f"{topic}.md"


def _ko(topic: str) -> Path:
    return USAGE_DIR / f"{topic}.ko.md"


def test_the_topic_list_is_the_directory():
    """A topic added on disk but not here is never checked for a twin or an index entry."""
    on_disk = {p.name.removesuffix(".ko.md").removesuffix(".md") for p in USAGE_DIR.glob("*.md")}
    assert on_disk == set(TOPICS)


@pytest.mark.parametrize("topic", TOPICS)
def test_every_topic_has_both_languages(topic: str):
    assert _en(topic).is_file(), f"docs/usage/{topic}.md is missing"
    assert _ko(topic).is_file(), f"docs/usage/{topic}.ko.md is missing"


@pytest.mark.parametrize(
    ("index", "suffix"), [("USAGE.md", ".md"), ("USAGE.ko.md", ".ko.md")]
)
def test_the_index_links_every_topic_in_its_language(index: str, suffix: str):
    text = (ROOT / index).read_text(encoding="utf-8")
    missing = [t for t in TOPICS if f"docs/usage/{t}{suffix})" not in text]
    assert not missing, f"{index} does not link {missing}"


def _docs() -> list[Path]:
    return [ROOT / "README.md", ROOT / "README.ko.md", ROOT / "USAGE.md", ROOT / "USAGE.ko.md"] + sorted(
        USAGE_DIR.glob("*.md")
    )


@pytest.mark.parametrize("doc", _docs(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_relative_link_and_anchor_resolves(doc: Path):
    text = doc.read_text(encoding="utf-8")
    broken = []
    for target in LINK.findall(_strip_code(text)):
        if re.match(r"^[a-z]+:", target):
            continue
        path, _, frag = target.partition("#")
        dest = (doc.parent / path).resolve() if path else doc
        if not dest.exists():
            broken.append(target)
        elif frag and dest.suffix == ".md" and not _has_anchor(dest.read_text(encoding="utf-8"), frag):
            broken.append(target)
    assert not broken, f"{doc.relative_to(ROOT).as_posix()} links to nothing at {broken}"
```

- [ ] **Step 2: `test_tier_table_parity.py` 경로 변경**

`TWINS = ("USAGE.md", "USAGE.ko.md")` → `TWINS = ("docs/usage/tiers-and-gates.md", "docs/usage/tiers-and-gates.ko.md")`. docstring 의 "both USAGE tables" → "both usage-guide tables".

- [ ] **Step 3: `test_shipped_contracts.py` 경로 변경**

`CONSUMER_DOCS` 를 README 두 개 + 언어별 usage 합본으로:

```python
USAGE_DIR = REPO / "docs" / "usage"


def _consumer_text(doc: str) -> str:
    """One README, or a whole usage guide in one language — a skill documented in any of
    that language's topic files is documented."""
    if doc == "docs/usage (en)":
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted(USAGE_DIR.glob("*.md")) if not p.name.endswith(".ko.md"))
    if doc == "docs/usage (ko)":
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted(USAGE_DIR.glob("*.ko.md")))
    return (REPO / doc).read_text(encoding="utf-8")


CONSUMER_DOCS = ("README.md", "README.ko.md", "docs/usage (en)", "docs/usage (ko)")
```

`test_every_consumer_facing_skill_is_registered` 의 `text = ...` 를 `text = _consumer_text(doc)` 로. `test_the_review_checklist_is_one_list_in_three_files` 의 루프 대상을 `("docs/usage/configuration.md", "docs/usage/configuration.ko.md")` 로. 긴 줄은 100자 안으로 나눔.

- [ ] **Step 4: 실패 확인**

Run: `uv run pytest tests/docs tests/skills/test_shipped_contracts.py -q`
Expected: FAIL — `docs/usage` 없음(twin·색인·parity·checklist).

### Task 2: 소스 결함 4건

**Files:**
- Modify: `flow-config.example.yaml`, `skills/flow-init/SKILL.md`, `skills/flow-init/references/setup-script-actions.md`, `skills/flow-uninstall/SKILL.md`, `scripts/check-deps.sh`

- [ ] **Step 1: `feature_prefix` 삭제** — `flow-config.example.yaml` 의 `feature_prefix:` 줄, flow-init SKILL.md Step 1 의 `/ `feature_prefix`` 토큰. `grep -rn feature_prefix skills rules scripts github flow-config.example.yaml` 결과 0건 확인(테스트 fixture 는 유지).
- [ ] **Step 2: `check-deps.sh`** — `anthropics/claude-code   (또는 해당 마켓)` → `anthropics/claude-plugins-official`; `Standard+ 작업 필수` → `Dev 작업 필수`; `Dev+ 에서 중단한다` → `Dev 에서 중단`. WSL: `wsl.exe -d Ubuntu -- bash -lc 'cd /mnt/c/Work/llm_ai/harness-tier && tr -d "\r" < scripts/check-deps.sh | shellcheck -'` → 경고 0.
- [ ] **Step 3: flow-uninstall SKILL.md Step 3** — `wiki-verify.yml` and `doc-style.yml` 문장을 `wiki-verify.yml`, `doc-style.yml` and `srs-verify.yml` 로, 호출 스크립트에 `srs_check.py` 추가. 먼저 `github/srs-verify.workflow.example.yml` 이 스크립트 부재 시 exit 0 가드를 갖는지 읽어 확인하고 문장을 그 동작대로.
- [ ] **Step 4: setup-script-actions.md** — unit-test 항목 뒤에 bullet 추가. `scripts/flow_init_setup.py` 의 `render_versioning_workflows` · `_RELEASE_TEMPLATES` 를 읽고: `versioning.enable` 이 true 일 때 `release_tool`(대소문자 무시)이 템플릿 5종 중 하나면 `release.yml`, 아니면 skip 보고; `branch_naming.enable` → `branch-naming.yml`; `entropy.enable` → `entropy-check.yml`(schedule 기본값); create-if-absent.
- [ ] **Step 5:** `uv run pytest tests/skills tests/flow_init -q` → 기존 green 유지.

### Task 3: 영문 주제 문서 — 설정·게이트 축

**Files:** Create `docs/usage/getting-started.md`, `configuration.md`, `tiers-and-gates.md`, `troubleshooting.md`, `update-and-removal.md`, `teams.md`

각 문서: H1 제목, 언어 링크 줄(`**English** · [한국어](<topic>.ko.md)`), 색인 링크 `[Usage guide](../../USAGE.md)`. 소스 확인 목록:

- [ ] **getting-started** — `USAGE.md` §1; 레이아웃 표에 `.claude/settings.json`(PreToolUse 게이트·marketplace), `.pre-commit-config.yaml`(없을 때 생성), `.gitignore` 두 줄, `CLAUDE.md` teams 블록, `.github/workflows/` 행 추가 — `scripts/flow_init_setup.py` `run_setup` 확인. `scripts/` 는 CI 가 호출하므로 추적 필요. `.flow/` 의 `tier`(브랜치 결속)·`<gate>.done`. 첫 실행 순서 `/harness-init` → `/flow-init` → `/flow`, `/flow-init` 첫 실행이 묻는 것(SKILL.md Step 1·2.6·2.7). `disable-model-invocation` 스킬 5개는 직접 입력.
- [ ] **configuration** — §2.1 예시 yaml 을 `flow-config.example.yaml` 과 대조(review_checklist 는 example 과 동일 5개), 모든 최상위 키 설명: `branches` · `merge_workflow`(promotion 에 hotfix 포함) · `modules`(`path` 일치 규칙은 `flow_gate_check.py` 확인) · `checks`+`when` 표 · `review_checklist` · `commit_guide` · `gate_evidence` · `doc_sync` · `wiki` · `doc_style` · `contract_test` · `unit_test` · `e2e` · `versioning` · `deploy`(상세는 deployments 링크). CI 섹션 상세는 ci-workflows 링크. `flow-tiers.yaml`: `/flow-init` 실행마다 덮어씀, 지속적 변경 수단 없음.
- [ ] **tiers-and-gates** — §2.3 표(파서가 읽는 형태 `| \`docs\` | ... | ✗ |` 유지), 검증 계층 정의 1회(pre-commit / 세션 게이트 / CI), 게이트별 설명, doc-style 커밋 단계 error 만(`flow_gate_check.doc_style_gate` 확인), evidence·무효화, §2.2 merge_strategy 표·범위(PR 모드 세부는 promotion-and-release 링크).
- [ ] **troubleshooting** — §6 전체 + 차단 메시지별 항목: evidence 누락, merge_strategy 위반, 모듈 사전검사 실패, wiki 구조 위반·stamp-only, `/flow-init` 판정 실패, 게이트 무반응 원인(`_gate_problems` 확인). 메시지 문자열은 스크립트에서 그대로 인용(한국어 원문 허용 — 인용 데이터).
- [ ] **update-and-removal** — §7 + §3.2 재실행 + §3.3. 업데이트 알림 동작, 재실행은 스크립트·정책만 재복사·워크플로 create-if-absent, `/flow-uninstall` 이 지우는 것·남기는 것·커밋 필요(`run_uninstall` 출력 확인), 수동 정리에 정확한 훅·두 줄·branch-naming·entropy-check·deploy 워크플로·`teams-notify-push`.
- [ ] **teams** — §4; 브랜치 채널은 pre-push 에서 브랜치명 일치 시(`notify-push.sh`), personal 미등록 시 안내 출력(`teams_alert.py`).
- [ ] 각 파일 `python scripts/doc_style_check.py --root . --lint docs/usage/<file>` → error 0.

### Task 4: 영문 주제 문서 — 스킬 축

**Files:** Create `docs/usage/daily-work.md`, `promotion-and-release.md`, `deployments.md`, `ci-workflows.md`, `project-harness.md`, `manual-verification.md`

- [ ] **daily-work** — §3.1(`/flow` 는 모든 작업·커밋의 첫 단계, 작업 브랜치 규칙, Docs/Dev 흐름 요약), `/commit` 절 신설(`skills/commit/SKILL.md` argument-hint·금지사항), §3.5 `/doc-sync`(`preview` 정확 인자, fork 실행, twin 동기화, 모듈 CLAUDE.md 생성 조건), §3.11 `/prose-review`(무손실 증명 원본).
- [ ] **promotion-and-release** — §3.10(`release.yml` 없으면 중단, 트레일러 조건, 토큰 점검은 경고), §2.1 merge_workflow·§2.2 PR/ruleset 문단(한 번만), 릴리스 토큰 절(렌더된 워크플로엔 preflight 없음 — `github/release.*` grep 확인).
- [ ] **deployments** — §3.8 + `maven-central`+gradle/sbt 의 `publish` 명령 예외.
- [ ] **ci-workflows** — 워크플로 카탈로그 표(파일 · 켜는 스위치 · 누가 렌더 · 막는가): api-contract, unit-test, e2e, doc-style, wiki-verify(`/wiki-init`), srs-verify(`/flow-init`, `docs/srs/` 존재 시), release(5종, CHANGELOG body 는 python-semantic-release 만), branch-naming(허용 패턴 고정), entropy-check, deploy. §3.7 E2E 블록. 모듈 check 는 명령별 timeout 없음·훅 600초(`GATE_ENTRY` 확인).
- [ ] **project-harness** — §3.4(인터뷰 선행, `.harness/` 근거 파일, code-style migrate 예외, 커밋하지 않음), 언어표(`## Auto-detected languages and frameworks` 제목 유지), §3.9 `/wiki-init`(선행조건, `wiki.enable`, verify 실패 시 되돌림), §3.6 `/harness-insight`.
- [ ] **manual-verification** — §3.7 스킬 3개: `/integration` web·Electron·non-web, `docs/verification/*.md` 우선, `/performance` BASE_URL 확인·도구 자동설치 없음, `/playwright-scaffold` config 수정·실행 안 함.
- [ ] 각 파일 doc-style lint error 0.

### Task 5: 한국어 twin 12개

**Files:** Create `docs/usage/*.ko.md`

- [ ] 영문 문서와 사실 1:1, 제목 구조 동일. 기존 `USAGE.ko.md` 의 용어 유지. 첫 줄 아래 `[English](<topic>.md) · **한국어**`, 색인 링크 `../../USAGE.ko.md`. 종결 `~함`/명사형.
- [ ] tiers-and-gates.ko 표 셀 `✓`/`✗` 유지, configuration.ko 의 review_checklist yaml 블록은 영문과 동일 문자열.
- [ ] doc-style lint error 0.

### Task 6: 색인·README·저장소 참조

**Files:** Modify `USAGE.md`, `USAGE.ko.md`, `README.md`, `README.ko.md`, `CLAUDE.md`, `.github/workflows/release.yml`, `flow-config.example.yaml`

- [ ] **USAGE 색인** — 제목, 언어 링크, "README 는 개요·설치, 이 색인은 주제별 문서" 한 줄, 표(문서 링크 · 답하는 질문) 12행, License 절 유지.
- [ ] **README(.ko)** — spec §2 README 항목 전부. 링크 갱신: 언어표 → `docs/usage/project-harness.md#auto-detected-languages-and-frameworks`, 토큰 → `docs/usage/promotion-and-release.md#release-token-write-permission`, 갱신·제거 "§7" → `docs/usage/update-and-removal.md`, 레이아웃 → `docs/usage/getting-started.md`. README 의 Update & removal 은 두 bullet 유지하되 링크만.
- [ ] **CLAUDE.md** — 첫 문단 "[USAGE.md](USAGE.md)" 문장에 `docs/usage/` 색인임을 반영; Folder structure `docs/` 줄: `internal design records (Korean, never shipped) · reference notes · usage/ consumer guide (English + .ko twins)`. 150줄 이내 유지.
- [ ] **release.yml** 2곳 `See USAGE.md → "Release token write permission".` → `See docs/usage/promotion-and-release.md → "Release token write permission".`; `(see job summary / USAGE.md)` → `(see job summary / docs/usage/promotion-and-release.md)`.
- [ ] **flow-config.example.yaml** E2E 주석 `see USAGE "E2E safety net"` → `see docs/usage/ci-workflows.md "E2E safety net"`.
- [ ] `grep -rn "USAGE" --include=*.py --include=*.yml --include=*.yaml --include=*.md . --exclude-dir=.venv --exclude-dir=docs/superpowers --exclude-dir=.superpowers --exclude-dir=graft` — 남은 참조가 색인을 뜻하는지 검토.

### Task 7: 검증

- [ ] `uv run pytest tests/docs tests/skills -q` → PASS.
- [ ] 전체 `uv run pytest -q` → PASS.
- [ ] Mutation(파이썬으로 적용, `assert old in text`, 복원은 파일 원본 보관 후 되쓰기 — 새 파일은 미추적이라 `git checkout --` 불가):
  1. `docs/usage/teams.ko.md` 이름 변경 → `test_every_topic_has_both_languages` FAIL.
  2. README 의 `#release-token-write-permission` → `#release-token-write-permissio` → 링크 테스트 FAIL.
  3. `USAGE.ko.md` 에서 `docs/usage/teams.ko.md)` 제거 → 색인 테스트 FAIL.
  각 mutation 적용 확인 후 복원, 기준선 green 재확인.
- [ ] `git ls-files -mo --exclude-standard '*.md' | xargs python scripts/doc_style_check.py --root . --lint` (docs/superpowers 제외) → error 0.
- [ ] 이전 USAGE.md 의 모든 H2/H3 주제가 새 문서 어딘가에 대응하는지 표로 확인(누락 0).
