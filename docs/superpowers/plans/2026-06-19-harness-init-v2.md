# harness-init v2 — 다중 에이전트 생성·비판 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** harness-init을 다중 에이전트(Agent Team) 리서치 + 사유 작성 + 경량 비판/검증 파이프라인으로 격상하고, reuse-before-build(무료 게이트)·기술문서 3종·커맨드 미생성을 반영한다.

**Architecture:** 플러그인 SOURCE(SSOT)에 신규 에이전트 2종·authoring references 5종·기술문서 템플릿 3종을 추가하고, `harness_scaffold.py`에 결정적 `validate` 서브커맨드를 더한다. harness-init SKILL이 detect→interview→research(팀 fan-out)→rationale→author→validate+critic(최대 2회)→preview→apply→report로 오케스트레이션한다. 모든 쓰기는 dual-path·덮어쓰기 금지·미리보기 확정을 유지한다.

**Tech Stack:** Python 3.8+ (게이트/스크립트, `uv run`) · pytest · PyYAML(폴백 라인파싱) · Markdown(에이전트/스킬/룰/문서) · Claude Code `Agent`(구 `Task`, alias) 서브에이전트 fan-out(표준; 교차대화는 Agent Teams 실험 기능 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 켜진 경우만 `SendMessage` 옵션).

## Global Constraints

- **dual-path**: 읽기 `${CLAUDE_PLUGIN_ROOT}`, 쓰기 `${CLAUDE_PROJECT_DIR}`. 플러그인 디렉터리에 쓰지 않는다.
- **덮어쓰기 금지**: 기존 파일은 `marker_upsert`(전용 마커블록)만, `create`는 부재 시만.
- **미리보기·확정 전 쓰기 금지**. harness-init은 **커밋하지 않는다**(/flow 책임).
- **Windows 인코딩**: 모든 Python은 `force_utf8_io()` 호출, 파일 IO는 `encoding="utf-8"`.
- **FAIL-OPEN**: `validate`는 게이트가 아니라 진단 — high 이슈에도 exit 0, JSON 리포트만 출력.
- **커맨드 미생성**: 어떤 산출물도 `.claude/commands/`에 생성하지 않는다.
- **flow 공존**: flow 감지(`.claude/vway-kit/config/flow-config.yaml`) 시 커밋·머지·PR 규율은 risk-tiers로 defer.
- 규율 SSOT는 [rules/harness-rules.md](../../../rules/harness-rules.md), 설계 SSOT는 [스펙](../specs/2026-06-19-harness-init-v2-design.md).
- 정적 검사 통과: `uv run ruff check && uv run ruff format --check && uv run pytest`.

## Shared Contract (모든 task가 동일하게 사용하는 이름)

- **증거 디렉터리**: `${CLAUDE_PROJECT_DIR}/.claude/vway-kit/.harness/` (gitignored). 파일:
  `research/<agent>_<topic>.md` · `rationale.md` · `plan.json` · `critic-report.json` · `manifest.json`.
- **baseline 마커**: `marker_id = "harness:baseline"`. 마커블록 본문에 필수 5종 룰 앵커 주입.
- **필수 5종 룰 키 + 앵커**: `karpathy` · `dry-constants` · `version-pinning` · `security` · `reuse-first`.
  각 룰 블록 첫 줄에 앵커 `<!-- rule:<key> -->`.
- **authoring reference 파일명**(`skills/harness-authoring/references/`):
  `karpathy-principles.md`(기존) · `rule-dry-constants.md`(기존) · `rule-version-pinning.md`(기존) ·
  `security-rule.md`(기존) · `rule-reuse-first.md`(신규) · `skill-writing-guide.md`(신규) ·
  `agent-design-guide.md`(신규) · `critique-guide.md`(신규) · `tech-doc-guide.md`(신규).
- **에이전트 이름**: `harness-researcher`(수정) · `harness-code-analyzer`(신규) · `harness-critic`(신규).
- **스크립트 서브커맨드**: `detect` · `apply` · `validate`(신규).
- **plan.json 스키마**(기존): `{"files": [{"path", "action": "create"|"marker_upsert", "content", "marker_id"?}]}`.
- **호스트 기술문서 경로**: `docs/ARCHITECTURE.md` · `docs/code-style.md` · `docs/onboarding.md`
  (기존 docs 디렉터리 관례 감지 시 그쪽 우선).
- **critic 리포트 스키마**: `{"issues":[{"severity":"high|med|low","file","kind":"quality|coherence|reuse|command","evidence","fix"}],"summary":{"high","med","low","verdict":"pass|revise"}}`.

## File Structure

| 파일 | 책임 |
|------|------|
| `skills/harness-authoring/references/rule-reuse-first.md` | reuse-before-build 룰 본문(무료 게이트) — baseline 주입 소스 |
| `rules/harness-rules.md` | 생성 규율 SSOT — 사유·critic·기술문서·팀·reuse·커맨드미생성 |
| `scripts/harness_scaffold.py` | `validate` 서브커맨드 + `_parse_frontmatter` 리팩터 |
| `tests/test_harness_scaffold.py` | validate 테스트 |
| `skills/harness-authoring/references/skill-writing-guide.md` | 스킬 작성 품질 가이드 |
| `skills/harness-authoring/references/agent-design-guide.md` | 에이전트 설계 가이드 |
| `skills/harness-authoring/references/critique-guide.md` | critic 검토 체크리스트(critic이 defer) |
| `skills/harness-authoring/references/tech-doc-guide.md` | 기술문서 작성법 |
| `skills/harness-authoring/templates/architecture.template.md` | ARCHITECTURE 골격 |
| `skills/harness-authoring/templates/code-style.template.md` | code-style 골격(BP·안티패턴·reuse) |
| `skills/harness-authoring/templates/onboarding.template.md` | onboarding 골격 |
| `skills/harness-authoring/templates/claude-md.template.md` | 5번째 룰 슬롯 + 앵커 추가 |
| `skills/harness-authoring/templates/{skill,agent,rule}.template.md` | 작성가이드 반영 강화 |
| `skills/harness-authoring/templates/command.template.md` | **삭제** |
| `agents/harness-code-analyzer.md` | 코드베이스 컨벤션·안티패턴·손수구현 추출(Explore) |
| `agents/harness-critic.md` | 생성물 비판(general-purpose) |
| `agents/harness-researcher.md` | 레지스트리 기성솔루션 탐색 + 팀 프로토콜 추가 |
| `skills/harness-authoring/SKILL.md` | references/templates/3종/기술문서 배선 |
| `skills/harness-init/SKILL.md` | v2 파이프라인·팀 오케스트레이션·폴백 |
| `README.md` · `USAGE.md` | harness 섹션 갱신 |

---

### Task 1: reuse-first 룰 본문 + 규율 SSOT 갱신

**Files:**
- Create: `skills/harness-authoring/references/rule-reuse-first.md`
- Modify: `rules/harness-rules.md`

**Interfaces:**
- Produces: reuse-first 룰 본문(Task 4 claude-md 템플릿의 `<!-- rule:reuse-first -->` 슬롯에 주입), 규율 항목(Task 5·6·7이 defer). 앵커는 템플릿이 소유 — reference 본문엔 넣지 않는다(중복 금지).

- [ ] **Step 1: rule-reuse-first.md 작성**

`skills/harness-authoring/references/rule-reuse-first.md` 생성. **앵커는 넣지 않는다**(claude-md 템플릿이 소유, 중복 금지). 내용(스펙 §7 확정 문구):

```markdown
### 재사용·기성 우선 (reuse-before-build)

직접 코드 구현 전에, **무료이면서 상용 사용이 허용되는** 기성 솔루션을 먼저 탐색·추천한다.

**탐색 범위(도구 기반)**: 공식 Docker 이미지, 표준 라이브러리, 프레임워크 빌트인,
패키지 레지스트리(Docker Hub·PyPI·npm 등)의 잘 유지되는 OSS.

**비용·라이선스 게이트**: 후보마다 비용(무료?)·라이선스(상용 가능?)·유지보수 상태를 확인하고,
**유료 솔루션(유료 매니지드 서비스·상용 라이선스·SaaS 구독)은 추천하지 않는다.**
무료·상용가능 후보가 없거나 요구사항에 부적합하면 직접 구현한다.
불확실한 라이선스/비용은 "확인 필요"로 표기하고 단정하지 않는다(지어내기 금지).

**Why**: 직접 구현은 유지보수·보안·엣지케이스 부담을 새로 떠안는다. 무료 OSS 기성품은 그 부담을
외부화하면서 비용·라이선스 제약도 없다. 단, 정당한 도메인 특화 구현까지 막지 않는다.
```

- [ ] **Step 2: harness-rules.md에 v2 규율 추가**

`rules/harness-rules.md`의 `## 산출물` 섹션에 항목 추가, 새 섹션 `## 다중 에이전트 / 비판` 추가. 정확히 추가할 블록:

```markdown
## 산출물 (추가)
10. **기술문서 3종**: `docs/ARCHITECTURE.md`(구조) · `docs/code-style.md`(행위적 스타일+BP+안티패턴) ·
    `docs/onboarding.md`(실행/디버그). 구조적 컨벤션은 룰, 행위적 스타일은 문서 — **한 사실 한 곳**(중복 금지).
11. **필수 룰 5종**: 기존 4종 + **reuse-first**([rule-reuse-first.md] 앵커 `<!-- rule:reuse-first -->`).
12. **커맨드 미생성**: 어떤 산출물도 `.claude/commands/`에 만들지 않는다(revfactory 정렬).

## 다중 에이전트 / 비판
13. **리서치는 `Agent`(구 `Task`) 서브에이전트 fan-out**(researcher + 브라운필드 시 code-analyzer) 병렬 디스패치·팬인. 교차대화는 Agent Teams 실험 기능 켜진 경우만 `SendMessage` 옵션.
    네트워크/팀 실패는 FAIL-OPEN(경고 + 사용자 선택), 지어내지 않는다.
14. **사유 작성**: research 종합 후 `.harness/rationale.md`(산출물별 생성 근거·채택 패턴·reuse 권고·출처).
15. **경량 비판**: `validate`(결정적 구조) → `harness-critic`(품질·정합성·reuse 위반·커맨드 미생성).
    재작성 최대 2회, 잔여는 "미해결"로 미리보기/보고에 명시(차단 금지).
```

- [ ] **Step 3: 검증**

Run: `grep -n "reuse-before-build" skills/harness-authoring/references/rule-reuse-first.md`
Expected: 룰 본문 출력(앵커는 reference 가 아니라 claude-md.template.md 의 reuse-first 슬롯에 존재). `rules/harness-rules.md`에 reuse-first·기술문서·커맨드 미생성 항목 존재 육안 확인.

- [ ] **Step 4: Commit**

```bash
git add skills/harness-authoring/references/rule-reuse-first.md rules/harness-rules.md
git commit -m "feat(harness): reuse-first 룰 본문 + v2 규율 SSOT 갱신"
```

---

### Task 2: `validate` 서브커맨드 (TDD)

**Files:**
- Modify: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: 기존 `scan_components`, `_marker_begin`, `_marker_end`, `_read_frontmatter`.
- Produces: `validate_plan(root: Path, plan: dict) -> {"ok": bool, "issues": [{"severity","kind","path","detail"}]}` (harness-init SKILL이 호출). `main(["validate","--root",R,"--plan",P])` → JSON 출력·exit 0.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_harness_scaffold.py` 끝에 추가:

```python
def _baseline_entry(extra_body=""):
    anchors = "".join(
        f"<!-- rule:{k} -->\n" for k in
        ("karpathy", "dry-constants", "version-pinning", "security", "reuse-first")
    )
    return {"path": "CLAUDE.md", "action": "marker_upsert",
            "marker_id": "harness:baseline", "content": anchors + extra_body}


def test_validate_ok_minimal(tmp_path):
    plan = {"files": [_baseline_entry()]}
    rep = hs.validate_plan(tmp_path, plan)
    assert rep["ok"] is True and rep["issues"] == []


def test_validate_missing_rule_anchor(tmp_path):
    e = _baseline_entry()
    e["content"] = e["content"].replace("<!-- rule:reuse-first -->\n", "")
    rep = hs.validate_plan(tmp_path, {"files": [e]})
    assert rep["ok"] is False
    assert any(i["kind"] == "rule-load" and "reuse-first" in i["detail"] for i in rep["issues"])


def test_validate_flags_command_generation(tmp_path):
    plan = {"files": [_baseline_entry(),
                      {"path": ".claude/commands/x.md", "action": "create", "content": "y"}]}
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "command" for i in rep["issues"]) and rep["ok"] is False


def test_validate_frontmatter_missing(tmp_path):
    plan = {"files": [_baseline_entry(),
                      {"path": ".claude/agents/a.md", "action": "create",
                       "content": "---\nname: \n---\nbody"}]}
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "frontmatter" for i in rep["issues"])


def test_validate_dedup_collision_with_existing(tmp_path):
    _write_component(tmp_path / ".claude" / "agents" / "dup.md", "dup", "Existing")
    plan = {"files": [_baseline_entry(),
                      {"path": ".claude/agents/new.md", "action": "create",
                       "content": "---\nname: dup\ndescription: New\n---\nbody"}]}
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "dedup" for i in rep["issues"])


def test_validate_dead_link(tmp_path):
    plan = {"files": [_baseline_entry(),
                      {"path": ".claude/agents/a.md", "action": "create",
                       "content": "---\nname: a\ndescription: d\n---\nsee [x](./missing.md)"}]}
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_dead_link_satisfied_by_plan(tmp_path):
    plan = {"files": [_baseline_entry(),
                      {"path": ".claude/agents/a.md", "action": "create",
                       "content": "---\nname: a\ndescription: d\n---\nsee [b](./b.md)"},
                      {"path": ".claude/agents/b.md", "action": "create",
                       "content": "---\nname: b\ndescription: d\n---\nx"}]}
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_no_baseline_marker(tmp_path):
    rep = hs.validate_plan(tmp_path, {"files": []})
    assert any(i["kind"] == "rule-load" for i in rep["issues"])


def test_main_validate_outputs_json_exit0(tmp_path, capsys):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"files": [_baseline_entry()]}), encoding="utf-8")
    rc = hs.main(["validate", "--root", str(tmp_path), "--plan", str(plan_file)])
    assert rc == 0  # FAIL-OPEN: 진단이지 게이트 아님
    out = json.loads(capsys.readouterr().out)
    assert "ok" in out and "issues" in out
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -k validate -v`
Expected: FAIL — `AttributeError: module 'scripts.harness_scaffold' has no attribute 'validate_plan'`.

- [ ] **Step 3: `_parse_frontmatter` 리팩터 + `validate_plan` 구현**

`scripts/harness_scaffold.py`에서 `_read_frontmatter`를 문자열 파서로 분리하고 상수·검증 함수 추가.

`_read_frontmatter`(line 179-201)를 다음으로 교체:

```python
def _parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(block) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    out: dict = {}
    for line in block.splitlines():
        mm = re.match(r"\s*(name|description)\s*:\s*(.+?)\s*$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip().strip("'\"")
    return out


def _read_frontmatter(md_path: Path) -> dict:
    try:
        return _parse_frontmatter(md_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
```

`apply_plan` 위에 검증 상수·함수 추가:

```python
REQUIRED_RULES = ("karpathy", "dry-constants", "version-pinning", "security", "reuse-first")
BASELINE_MARKER = "harness:baseline"
_SKILL_PATH_RE = re.compile(r"(?:^|/)\.claude/skills/[^/]+/SKILL\.md$")
_AGENT_PATH_RE = re.compile(r"(?:^|/)\.claude/agents/[^/]+\.md$")
_MD_LINK_RE = re.compile(r"\]\(([^)]+?\.md)(?:#[^)]*)?\)")


def _is_component_path(rel: str) -> bool:
    return bool(_SKILL_PATH_RE.search(rel) or _AGENT_PATH_RE.search(rel))


def validate_plan(root: Path, plan: dict) -> dict:
    issues: list[dict] = []
    files = plan.get("files", [])
    plan_paths = {e.get("path", "").replace("\\", "/") for e in files}

    existing = scan_components(root / ".claude")
    existing_names = {c["name"] for grp in existing.values() for c in grp if c.get("name")}
    new_names: set[str] = set()

    for e in files:
        rel = e.get("path", "").replace("\\", "/")
        content = e.get("content", "")

        if rel.startswith(".claude/commands/") or "/.claude/commands/" in rel:
            issues.append({"severity": "high", "kind": "command", "path": rel,
                           "detail": "harness는 커맨드를 생성하지 않는다"})

        if _is_component_path(rel):
            fm = _parse_frontmatter(content)
            if not fm.get("name"):
                issues.append({"severity": "high", "kind": "frontmatter", "path": rel,
                               "detail": "name 누락/빈값"})
            if not fm.get("description"):
                issues.append({"severity": "high", "kind": "frontmatter", "path": rel,
                               "detail": "description 누락/빈값"})
            nm = fm.get("name", "")
            if nm and nm in existing_names:
                issues.append({"severity": "high", "kind": "dedup", "path": rel,
                               "detail": f"기존 컴포넌트와 name 충돌: {nm}"})
            if nm and nm in new_names:
                issues.append({"severity": "high", "kind": "dedup", "path": rel,
                               "detail": f"plan 내 name 중복: {nm}"})
            if nm:
                new_names.add(nm)

        for link in _MD_LINK_RE.findall(content):
            if link.startswith(("http://", "https://", "/")):
                continue
            target = os.path.normpath(str(Path(rel).parent / link)).replace("\\", "/")
            if target in plan_paths or (root / target).exists():
                continue
            issues.append({"severity": "warn", "kind": "dead-link", "path": rel,
                           "detail": f"링크 대상 없음: {link}"})

        if e.get("action") == "marker_upsert":
            target_file = root / rel
            if target_file.exists():
                txt = target_file.read_text(encoding="utf-8")
                mid = e.get("marker_id", "")
                if _marker_begin(mid) in txt and _marker_end(mid) not in txt:
                    issues.append({"severity": "high", "kind": "marker", "path": rel,
                                   "detail": "BEGIN without END (corrupt)"})

    baseline = next((e for e in files if e.get("action") == "marker_upsert"
                     and e.get("marker_id") == BASELINE_MARKER), None)
    if baseline is None:
        issues.append({"severity": "high", "kind": "rule-load", "path": "CLAUDE.md",
                       "detail": f"{BASELINE_MARKER} 마커블록 없음"})
    else:
        body = baseline.get("content", "")
        for key in REQUIRED_RULES:
            if f"<!-- rule:{key} -->" not in body:
                issues.append({"severity": "high", "kind": "rule-load",
                               "path": baseline.get("path", "CLAUDE.md"),
                               "detail": f"필수 룰 anchor 누락: {key}"})

    return {"ok": not any(i["severity"] == "high" for i in issues), "issues": issues}
```

`main`의 subparser에 validate 추가(`apply` 블록 뒤, line 296 부근):

```python
    v = sub.add_parser("validate")
    v.add_argument("--root", default=".")
    v.add_argument("--plan", required=True)
```

그리고 `if args.cmd == "apply":` 블록 뒤에:

```python
    if args.cmd == "validate":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        print(json.dumps(validate_plan(root, plan), ensure_ascii=False, indent=2))
        return 0  # FAIL-OPEN: 진단이지 게이트가 아님
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -v`
Expected: 전체 PASS(기존 + 신규 validate 9개).

- [ ] **Step 5: 린트 + 커밋**

Run: `uv run ruff check scripts/harness_scaffold.py tests/test_harness_scaffold.py && uv run ruff format --check scripts/harness_scaffold.py`
Expected: 통과.
```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(harness): validate 서브커맨드 — 결정적 구조 검증(FAIL-OPEN)"
```

---

### Task 3: authoring 작성 품질 references (4종)

**Files:**
- Create: `skills/harness-authoring/references/skill-writing-guide.md`
- Create: `skills/harness-authoring/references/agent-design-guide.md`
- Create: `skills/harness-authoring/references/critique-guide.md`
- Create: `skills/harness-authoring/references/tech-doc-guide.md`

**Interfaces:**
- Produces: 작성가이드(Task 6 authoring SKILL이 로드), critique 체크리스트(Task 5 critic이 defer).

> 각 파일은 revfactory 원문을 vway-kit 톤(명령형·한글·간결)으로 **압축 차용**. 각 ≤ 400줄, 300줄 초과 시 상단 목차.

- [ ] **Step 1: skill-writing-guide.md**

섹션(차용 소스 = revfactory skill-writing-guide §1–9): ① pushy Description 패턴(트리거 적극화·경계조건) ② Why-First 본문 ③ 일반화/오버피팅 금지 ④ 출력형식·예시 ⑤ Progressive Disclosure(도메인 분리·조건부 상세·300줄 목차) ⑥ 컨텍스트 절약 ⑦ 스크립트 번들링 신호 ⑧ 스킬에 넣지 말 것 ⑨ 재사용 설계(중복검토). 핵심 원칙: "한 스킬 한 역할".

- [ ] **Step 2: agent-design-guide.md**

섹션(소스 = revfactory agent-design-patterns): ① 분리 기준(전문성·병렬성·컨텍스트·재사용성) ② 중복검토(재사용 설계 표) ③ 에이전트 정의 구조(역할/원칙/입출력/에러/협업/**팀 통신 프로토콜**) ④ 빌트인 타입 선택(general-purpose/Explore/Plan) ⑤ 스킬↔에이전트 연결 방식. **팀 모드 기본** 명시.

- [ ] **Step 3: critique-guide.md**

critic이 defer하는 검토 체크리스트: ① 작성 품질(description 적극성·Why-first·lean·일반화·로드경로 위반) ② 경계면 정합성(CLAUDE.md↔룰 로드, 산출물 상호참조, dead-link, 마커 정합) ③ **reuse 위반**(무료 기성 대신 재발명, 또는 유료 추천) ④ 커맨드 미생성 재확인 ⑤ 드라이런(생성물이 실제 트리거/로드되는가). 출력 = Shared Contract의 critic 리포트 스키마.

- [ ] **Step 4: tech-doc-guide.md**

기술문서 3종 작성법: ① ARCHITECTURE.md(프레임워크·폴더구조·주요모듈·데이터흐름; 브라운필드면 code-analyzer 스캔값·출처) ② code-style.md(네이밍·포맷·임포트 + **베스트프랙티스** + **안티패턴**(바퀴 재발명 포함) + reuse 구체 예시) ③ onboarding.md(실행·브랜치·디버그). SSOT 분리 원칙(구조=룰, 행위=문서) 재강조.

- [ ] **Step 5: 검증**

Run: `for f in skill-writing-guide agent-design-guide critique-guide tech-doc-guide; do wc -l skills/harness-authoring/references/$f.md; done`
Expected: 각 파일 존재·≤400줄. 300줄 초과 파일은 목차 포함 육안 확인.

- [ ] **Step 6: Commit**

```bash
git add skills/harness-authoring/references/skill-writing-guide.md skills/harness-authoring/references/agent-design-guide.md skills/harness-authoring/references/critique-guide.md skills/harness-authoring/references/tech-doc-guide.md
git commit -m "feat(harness): authoring 작성 품질 references 4종 차용"
```

---

### Task 4: 템플릿 — 기술문서 3종 신규 + 기존 강화 + command 삭제

**Files:**
- Create: `skills/harness-authoring/templates/architecture.template.md`
- Create: `skills/harness-authoring/templates/code-style.template.md`
- Create: `skills/harness-authoring/templates/onboarding.template.md`
- Modify: `skills/harness-authoring/templates/claude-md.template.md`
- Modify: `skills/harness-authoring/templates/{skill,agent,rule}.template.md`
- Delete: `skills/harness-authoring/templates/command.template.md`

**Interfaces:**
- Consumes: 룰 앵커(Task 1), 작성가이드(Task 3).
- Produces: 템플릿(Task 6 authoring·Task 7 init이 채움).

- [ ] **Step 1: claude-md.template.md에 5번째 룰 슬롯 + 앵커 추가**

기존 baseline 마커블록(line 8-14)을 교체 — 각 룰에 앵커 추가 + reuse-first 슬롯:

```markdown
<!-- harness:baseline BEGIN (managed by /harness-init — edits inside are overwritten) -->
## 필수 작업 원칙
<!-- rule:karpathy -->
{{KARPATHY_PRINCIPLES}}
<!-- rule:dry-constants -->
{{DRY_CONSTANTS}}
<!-- rule:version-pinning -->
{{VERSION_PINNING}}
<!-- rule:security -->
{{SECURITY}}
<!-- rule:reuse-first -->
{{REUSE_FIRST}}
<!-- harness:baseline END -->
```

- [ ] **Step 2: 기술문서 템플릿 3종 작성**

`architecture.template.md`:
```markdown
# {{PROJECT_NAME}} 아키텍처

## 스택 / 프레임워크
{{FRAMEWORK}} {{VERSION}} — {{STACK_SUMMARY}}  <!-- 출처: {{SOURCES}} -->

## 폴더 구조
{{FOLDER_MAP}}

## 주요 모듈 / 데이터 흐름
{{MODULES_AND_FLOW}}
```

`code-style.template.md`:
```markdown
# {{PROJECT_NAME}} 코드 스타일

## 네이밍 · 포맷 · 임포트
{{STYLE_RULES}}  <!-- 출처: {{SOURCES}} -->

## 베스트 프랙티스
{{BEST_PRACTICES}}

## 안티패턴 (피한다)
{{ANTI_PATTERNS}}
- **바퀴 재발명**: 무료·상용가능 기성 솔루션(공식 이미지·표준 라이브러리·OSS)이 있으면 직접 구현 대신 사용.
{{REUSE_EXAMPLES}}
```

`onboarding.template.md`:
```markdown
# {{PROJECT_NAME}} 온보딩

## 실행
{{RUN_COMMANDS}}

## 브랜치 / 워크플로
{{BRANCH_FLOW}}

## 디버그
{{DEBUG_NOTES}}
```

- [ ] **Step 3: skill/agent/rule 템플릿 강화**

`agent.template.md`에 팀 통신·에러·협업 섹션 추가:
```markdown
---
name: {{AGENT_NAME}}
description: {{WHEN_TO_USE_WITH_EXAMPLES_PUSHY}}
model: {{MODEL_OR_REMOVE}}
---

You are {{ROLE}}. {{SINGLE_RESPONSIBILITY}}

## 핵심 역할
- {{R1}}

## 작업 원칙
- {{P1}}

## 입력 / 출력 프로토콜
- 입력: {{INPUT}}
- 출력: {{OUTPUT_PATH_AND_FORMAT}}

## 팀 통신 프로토콜 (팀 모드)
- 수신: {{FROM_WHOM_WHAT}}
- 발신: {{TO_WHOM_WHAT}}

## 에러 핸들링
- {{ON_FAILURE}}
```

`skill.template.md`·`rule.template.md`는 description을 `{{..._PUSHY}}`로, 본문 첫 섹션에 `## Why`(맥락) 슬롯 추가(작성가이드 Why-first 반영). 기존 구조 유지하며 슬롯만 보강.

- [ ] **Step 4: command.template.md 삭제**

```bash
git rm skills/harness-authoring/templates/command.template.md
```

- [ ] **Step 5: 검증**

Run: `ls skills/harness-authoring/templates/ && grep -c "rule:" skills/harness-authoring/templates/claude-md.template.md`
Expected: command.template.md 없음, architecture/code-style/onboarding 존재, claude-md에 앵커 5개.

- [ ] **Step 6: Commit**

```bash
git add skills/harness-authoring/templates/
git commit -m "feat(harness): 기술문서 템플릿 3종 + 룰 앵커·팀 프로토콜 슬롯, command 템플릿 삭제"
```

---

### Task 5: 에이전트 — code-analyzer·critic 신규, researcher 강화

**Files:**
- Create: `agents/harness-code-analyzer.md`
- Create: `agents/harness-critic.md`
- Modify: `agents/harness-researcher.md`

**Interfaces:**
- Consumes: critique-guide(Task 3), reuse-first 룰(Task 1), critic 리포트 스키마(Shared Contract).
- Produces: 에이전트 정의(Task 7 init이 팀 멤버로 디스패치). 이름은 Shared Contract 고정.

- [ ] **Step 1: harness-code-analyzer.md 작성**

frontmatter `name: harness-code-analyzer`, description은 pushy + 예시. 본문: Explore 타입(읽기전용), 역할=코드베이스에서 ① 실제 코드스타일(네이밍·포맷·임포트) ② 반복 패턴 ③ 안티패턴 ④ **손수 구현했는데 무료 기성품으로 대체 가능한 것** 추출, 각 항목 출처(파일:라인). 출력 `.harness/research/code-analyzer_<topic>.md`. 팀 통신 프로토콜: researcher에게 "손수구현 X 발견 — 무료 대체 조사 요청" SendMessage. 라이선스/유료 판정은 researcher 위임.

- [ ] **Step 2: harness-critic.md 작성**

frontmatter `name: harness-critic`, general-purpose(Read/Grep/validate 실행). 본문: critique-guide를 defer해 plan+생성파일 검토. 검토 4영역(품질·정합성·reuse 위반(유료 추천 포함)·커맨드 미생성). 출력 = critic 리포트 스키마(`.harness/critic-report.json`). `verdict: revise`면 리더가 최대 2회 재작성하도록 이슈별 `fix` 명시. 무한루프 금지 인지.

- [ ] **Step 3: harness-researcher.md 강화**

기존 `agents/harness-researcher.md` 수정: ① 출력 형식에 "### 기성 솔루션 후보(무료·상용가능)" 섹션 추가 — 후보별 `이름 / 비용(무료?) / 라이선스(상용 가능?) / 유지보수 / 출처`, **유료는 제외** ② 레지스트리(Docker Hub·PyPI·npm) 조회 절차 추가 ③ "### 안티패턴" 항목 추가 ④ "## 팀 통신 프로토콜" 섹션 추가(code-analyzer로부터 "손수구현 X" 수신 → 무료 대체 조사 → 회신). 불확실 라이선스/비용은 "확인 필요" 표기.

- [ ] **Step 4: 검증 (validate로 frontmatter·이름 자가검사)**

Run: 임시 plan으로 3개 에이전트 frontmatter 검증 —
```bash
uv run python -c "import json,scripts.harness_scaffold as h,pathlib as p; print([h._read_frontmatter(p.Path('agents')/f).get('name') for f in ('harness-code-analyzer.md','harness-critic.md','harness-researcher.md')])"
```
Expected: `['harness-code-analyzer', 'harness-critic', 'harness-researcher']`.

- [ ] **Step 5: Commit**

```bash
git add agents/harness-code-analyzer.md agents/harness-critic.md agents/harness-researcher.md
git commit -m "feat(harness): code-analyzer·critic 에이전트 신규 + researcher 기성솔루션 탐색 강화"
```

---

### Task 6: harness-authoring SKILL 배선

**Files:**
- Modify: `skills/harness-authoring/SKILL.md`

**Interfaces:**
- Consumes: references 5종(Task 1·3), 템플릿(Task 4).
- Produces: 채워진 산출물 + plan.json(Task 7 init이 호출).

- [ ] **Step 1: SKILL.md 갱신**

① 산출물 3종(skill/agent/rule)+기술문서 3종 명시, **command 제거**. ② 필수 룰 5종(reuse-first 포함) baseline 마커블록 주입 — 앵커 보존. ③ 작성 품질 references 로드 지시(skill-writing·agent-design·tech-doc-guide). ④ flow 감지 시 프로세스 룰 emit 금지(risk-tiers defer) 유지. ⑤ SSOT 분리(구조=룰, 행위=문서) 명시.

- [ ] **Step 2: 검증**

Run: `grep -nE "command|reuse-first|code-style" skills/harness-authoring/SKILL.md`
Expected: command 생성 언급 없음(또는 "미생성"만), reuse-first·기술문서 언급 존재.

- [ ] **Step 3: Commit**

```bash
git add skills/harness-authoring/SKILL.md
git commit -m "feat(harness): authoring SKILL — 5종 룰·기술문서·작성가이드 배선, command 제거"
```

---

### Task 7: harness-init SKILL — v2 파이프라인·팀 오케스트레이션

**Files:**
- Modify: `skills/harness-init/SKILL.md`

**Interfaces:**
- Consumes: validate(Task 2), 에이전트 3종(Task 5), authoring(Task 6), 룰/규율(Task 1).

- [ ] **Step 1: frontmatter allowed-tools 갱신**

allowed-tools 는 표준 도구만: `Bash, Read, Write, Edit, AskUserQuestion, Glob, Grep, Agent, SendMessage, WebSearch, WebFetch, Skill`. `Agent` 는 v2.1.63+ 의 정식 서브에이전트 도구(구 `Task`, alias). `SendMessage` 는 Agent Teams 실험 기능 켜진 경우의 교차대화 옵션용이며, 폐기된 `TeamCreate`/`TaskCreate`/`TeamDelete` 는 넣지 않는다.

- [ ] **Step 2: 파이프라인 본문 재작성 (스펙 §4·§5)**

Step 0 detect 유지. Step 1 인터뷰에서 **command 선택지 제거**, 기술문서 3종 추가. Step 2 리서치 = `Agent`(구 `Task`) 서브에이전트 fan-out(researcher + 브라운필드 시 code-analyzer 병렬 디스패치·팬인) → 산출 `.harness/research/*.md`; **교차대화는 Agent Teams 실험 기능 켜진 경우만 `SendMessage` 옵션**(폐기 도구 미사용) 명시. Step 3 사유 작성 `.harness/rationale.md`. Step 4 authoring → plan.json. Step 5 비판: `validate` 실행 → `harness-critic` 디스패치 → `verdict: revise`면 authoring 재작성 **최대 2회** → 잔여 "미해결" 명시. Step 6 미리보기(plan+rationale+critic). Step 7 apply. Step 8 manifest + 보고, 커밋 안 함.

- [ ] **Step 3: critical rules·경로 보강**

`.harness/` 하위 증거 파일 목록(Shared Contract) 명시. 첫 쓰기 전 `.gitignore` 멱등 추가 유지. FAIL-OPEN(팀/네트워크 실패 시 경고+선택).

- [ ] **Step 4: 검증**

Run: `grep -nE "서브에이전트 fan-out|code-analyzer|harness-critic|validate|rationale|교차대화" skills/harness-init/SKILL.md`
Expected: 팀 오케스트레이션·폴백·critic·rationale·validate 모두 언급. command 인터뷰 선택지 없음.

- [ ] **Step 5: Commit**

```bash
git add skills/harness-init/SKILL.md
git commit -m "feat(harness): init SKILL v2 — 팀 fan-out·사유·비판 루프 파이프라인"
```

---

### Task 8: 문서 동기화 (README·USAGE)

**Files:**
- Modify: `README.md`
- Modify: `USAGE.md`

- [ ] **Step 1: USAGE.md harness 섹션 갱신**

§6 동작 방식: v2 파이프라인(검증→인터뷰→**팀 리서치**→**사유**→생성→**비판/검증**→미리보기→확정). 에이전트 목록(line 564)에 `harness-code-analyzer · harness-critic` 추가. 산출물에 기술문서 3종 추가, **커맨드 미생성** 명시.

- [ ] **Step 2: README.md 갱신**

harness-init 한줄 설명에 다중 에이전트·비판·기술문서 반영(있는 범위에서). 컴포넌트 목록에 신규 에이전트 2종 추가.

- [ ] **Step 3: 검증**

Run: `grep -nE "code-analyzer|harness-critic" USAGE.md README.md`
Expected: 양쪽에 신규 에이전트 언급.

- [ ] **Step 4: Commit**

```bash
git add README.md USAGE.md
git commit -m "docs(harness): v2 파이프라인·신규 에이전트·기술문서 반영"
```

---

### Task 9: 최종 검증 + 독립 critic 리뷰 패스

**Files:** (수정 발생 시 해당 파일)

- [ ] **Step 1: 전체 정적 검사**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check && uv run pre-commit run --all-files`
Expected: 전체 통과.

- [ ] **Step 2: 독립 critic 리뷰 서브에이전트 디스패치**

별도 서브에이전트(Explore/general-purpose)로 전체 변경을 교차검토: ① 이름 일치(에이전트명·룰 키·앵커·서브커맨드가 모든 파일에서 동일한가) ② dead-link(references↔SKILL↔템플릿 상호참조) ③ Shared Contract 위반 ④ 불변(덮어쓰기 금지·dual-path·커맨드 미생성·Windows 인코딩) 누락. 구조화 리포트 반환.

- [ ] **Step 3: 리포트 반영**

발견 이슈를 해당 파일에서 수정. 재검사(Step 1) 통과 확인.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "fix(harness): 최종 critic 리뷰 반영 — 이름 일치·dead-link·불변 보강"
```

---

## Self-Review

**1. Spec coverage**
- §4 파이프라인 8단계 → Task 7(init SKILL). ✅
- §5 팀 오케스트레이션·폴백 → Task 7 Step 2. ✅
- §6 산출물(기술문서 3종·증거) → Task 4(템플릿)·Task 7(경로). ✅
- §7 reuse-first 5번째 룰 → Task 1(본문)·Task 4(앵커 슬롯)·Task 2(검증). ✅
- §8 컴포넌트 17개 → Task 1–8 전부 매핑. ✅
- §9 validate 6검사 → Task 2 테스트 9개(rule-load·command·frontmatter·dedup·dead-link×2·no-baseline·main). ✅
- §10 critic 스키마 → Task 5 Step 2 + Shared Contract. ✅
- §12 테스트 → Task 2. ✅
- 커맨드 미생성(§3 D) → Task 4(삭제)·Task 2(검사)·Task 6·7(제거). ✅

**2. Placeholder scan**: 코드 step은 전부 실제 코드. 문서 step은 섹션·키포인트·소스 명시(vague "적절히" 없음). `{{...}}`는 템플릿 슬롯(의도된 placeholder). ✅

**3. Type consistency**: `validate_plan(root, plan) -> {"ok","issues"}` — Task 2 정의 ↔ Task 7 호출 일치. 룰 키 `reuse-first`·앵커 `<!-- rule:reuse-first -->` — Task 1·2·4 동일. 에이전트명 `harness-code-analyzer`/`harness-critic`/`harness-researcher` — Task 5·7·8 동일. `REQUIRED_RULES` 5종 — Task 2 코드 ↔ Task 4 앵커 슬롯 일치. ✅
