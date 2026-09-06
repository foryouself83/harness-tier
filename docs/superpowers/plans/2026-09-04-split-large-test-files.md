# 500줄 초과 테스트 파일 분류 폴더 분할 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 500줄을 넘는 `tests/*.py` 8개를 대상 모듈 이름의 패키지로 쪼개고, 그 기준을 CLAUDE.md 규칙으로 못박는다.

**Architecture:** 손으로 옮기지 않는다. AST로 최상위 구문을 읽어 파일별로 나누고, 두 파일 이상이 쓰는 이름만 `_helpers.py`로 올리고, 픽스처는 `conftest.py`로 보내는 일회용 분할기를 scratchpad에 쓴 뒤 8번 돌린다. 각 폴더는 `__init__.py`를 갖는 패키지 — 그래야 `tests/gate/test_merge.py`와 `tests/wiki_graph/test_build.py`처럼 basename이 겹쳐도 pytest가 import mismatch를 내지 않고, `from tests.<pkg>._helpers import ...`가 성립한다.

**Tech Stack:** Python 3.12 · pytest · ruff · uv · `ast` 표준 라이브러리

**Spec:** 대화에서 확정한 요구사항 (이 문서 "Global Constraints"가 그 전문)

## Global Constraints

- 대상은 **500줄 초과** 파일 8개뿐. 500줄 이하 12개는 `tests/` 루트에 그대로 둔다.
- 분할 결과물도 **파일당 500줄 이하**.
- **테스트가 사라지거나 의미가 바뀌면 안 된다.** 검증은 `uv run pytest --collect-only -q`의 node id 집합이 파일 경로를 뗀 기준으로 분할 전후 동일할 것 — 기준선 **1786 collected**.
- 폴더 이름은 대상 모듈 이름을 그대로 쓴다: `flow_init` · `flow_gate` · `wiki_graph` · `evals` · `harness_paths` · `harness_scaffold` · `skills` · `merge_ruleset`.
- 테스트 본문은 **한 글자도 고치지 않는다**. 옮기는 것 외의 편집은 이 작업의 범위가 아니다.
- 공유 심볼은 `_helpers.py`, 픽스처(`@pytest.fixture`)는 `conftest.py`, 원본 모듈 docstring은 패키지 `__init__.py`.
- 저장소 규약대로 **주석·docstring은 영어**. 분할기가 새로 만드는 텍스트는 최소한으로.
- `uv run ruff check && uv run ruff format --check` 통과. 쓰지 않는 import를 남기면 F401로 잡히므로 분할기가 import를 사용 이름 기준으로 걸러야 한다.
- 분할기 자체는 **커밋하지 않는다** — scratchpad에만 둔다.
- `.github/workflows/doc-style.yml`의 `git ls-files 'tests/*.py'`는 손대지 않는다. git pathspec의 `*`는 `/`를 넘으므로 하위 폴더까지 이미 잡힌다(측정으로 확인함).

---

### Task 1: 분할기 작성 및 최소 대상 검증

**Files:**
- Create: `<scratchpad>/split_tests.py`
- Test: 실행 결과가 곧 테스트 — `tests/merge_ruleset/`를 만들어 pytest로 확인

`<scratchpad>` =
`C:/Users/USER/AppData/Local/Temp/claude/c--Work-llm-ai-harness-tier/478c1a26-6c15-4004-a2f6-ead7192a464e/scratchpad`

**Interfaces:**
- Produces: 기준선 파일 `<scratchpad>/before.txt` (분할 전 node id 이름 집합) 과
  `python split_tests.py <source.py> <package-dir> <spec.json>` — `spec.json`은
  `[{"module": "test_x", "anchor": "test_first_name_in_this_file"}, ...]` 순서 목록. anchor는
  그 파일이 가져갈 **첫 최상위 구문의 이름**(테스트 함수명 또는 헬퍼/상수명)이다. 앞 구문부터
  다음 anchor 직전까지가 그 모듈 몫.

- [ ] **Step 0: 기준선 node id를 먼저 잡는다** — 트리를 건드리기 전에만 잡을 수 있다.

```bash
uv run pytest --collect-only -q 2>/dev/null | grep '::' | sed 's/.*:://' | sort > "<scratchpad>/before.txt"
wc -l < "<scratchpad>/before.txt"
```

Expected: 1786.

- [ ] **Step 1: 분할기를 쓴다**

```python
"""One-shot splitter for oversized pytest modules. Scratchpad-only, never committed."""

import ast
import json
import sys
from pathlib import Path

FIXTURE = "fixture"


def _binds(node):
    """Module-level names this top-level statement introduces."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in node.names}
    return set()


def _uses(node):
    # Names only. An attribute's root is a Name too, and counting `.attr` would hoist an
    # import for every method that happens to share a module's name.
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _is_fixture(node):
    return isinstance(node, ast.FunctionDef) and any(
        FIXTURE in ast.unparse(d) for d in node.decorator_list
    )


def _segments(src):
    """Every top-level statement with the raw source that precedes it, so no comment is lost."""
    lines = src.splitlines(keepends=True)
    body = ast.parse(src).body
    segs, prev_end = [], 0
    for node in body:
        first = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
        lead = lines[prev_end : first - 1]
        while lead and not lead[0].strip():
            lead.pop(0)
        segs.append(
            {
                "node": node,
                "text": "".join(lead) + "".join(lines[first - 1 : node.end_lineno]),
                "binds": _binds(node),
                "uses": _uses(node),
            }
        )
        prev_end = node.end_lineno
    if segs:
        segs[-1]["text"] += "".join(lines[prev_end:])
    return segs


def _import_line(node, wanted):
    """The import statement narrowed to the aliases actually used, or None."""
    keep = [a for a in node.names if (a.asname or a.name).split(".")[0] in wanted]
    if not keep:
        return None
    clone = type(node)(**{**node.__dict__, "names": keep})
    return ast.unparse(ast.fix_missing_locations(clone))


def split(source: Path, pkg: Path, spec):
    src = source.read_text(encoding="utf-8")
    segs = _segments(src)

    doc = None
    if segs and isinstance(segs[0]["node"], ast.Expr) and isinstance(
        segs[0]["node"].value, ast.Constant
    ):
        doc = segs.pop(0)

    anchors = {entry["anchor"]: entry["module"] for entry in spec}
    order = [entry["module"] for entry in spec]

    imports, current, owner = [], None, {m: [] for m in order}
    prelude, fixtures = [], []
    for seg in segs:
        if isinstance(seg["node"], (ast.Import, ast.ImportFrom)):
            imports.append(seg)
            continue
        hit = anchors.keys() & seg["binds"]
        if hit:
            current = anchors[next(iter(hit))]
        if _is_fixture(seg["node"]):
            fixtures.append(seg)
        elif current is None:
            prelude.append(seg)
        else:
            owner[current].append(seg)

    # A definition read from anywhere but its own module is shared; so is anything the
    # prelude or a fixture holds, and anything those shared definitions read in turn.
    shared = list(prelude)
    moved = True
    while moved:
        moved = False
        pool = {n for s in shared + fixtures for n in s["uses"]}
        for module in order:
            for seg in list(owner[module]):
                readers = {
                    other
                    for other in order
                    if other != module
                    and any(seg["binds"] & s["uses"] for s in owner[other])
                }
                if readers or seg["binds"] & pool:
                    owner[module].remove(seg)
                    shared.append(seg)
                    moved = True

    shared.sort(key=lambda s: s["node"].lineno)
    pkg.mkdir(parents=True, exist_ok=True)

    def emit(path, segments, extra_import=None):
        used = {n for s in segments for n in s["uses"]}
        head = [line for s in imports if (line := _import_line(s["node"], used))]
        if extra_import:
            names = sorted(n for s in shared for n in s["binds"] if n in used)
            if names:
                head.append(f"from {extra_import} import {', '.join(names)}")
        text = "\n".join(head) + "\n\n" + "".join(s["text"] for s in segments)
        path.write_text(text.lstrip("\n"), encoding="utf-8")

    (pkg / "__init__.py").write_text(doc["text"] if doc else "", encoding="utf-8")
    dotted = f"tests.{pkg.name}._helpers"
    if shared:
        emit(pkg / "_helpers.py", shared)
    if fixtures:
        emit(pkg / "conftest.py", fixtures, extra_import=dotted if shared else None)
    for module in order:
        emit(pkg / f"{module}.py", owner[module], extra_import=dotted if shared else None)


if __name__ == "__main__":
    src, out, spec_file = sys.argv[1:4]
    split(Path(src), Path(out), json.loads(Path(spec_file).read_text(encoding="utf-8")))
```

- [ ] **Step 2: 가장 작은 대상으로 돌려본다**

`<scratchpad>/spec-merge-ruleset.json`:

```json
[
  {"module": "test_method_match", "anchor": "test_exact_match_exits_0"},
  {"module": "test_bypass", "anchor": "test_bypass_actor_present_exits_0"},
  {"module": "test_decoding", "anchor": "_cp949_env"},
  {"module": "test_dispatch", "anchor": "_body"},
  {"module": "test_step_27", "anchor": "SKILL"}
]
```

Run:

```bash
uv run python "<scratchpad>/split_tests.py" tests/test_check_merge_ruleset.py tests/merge_ruleset "<scratchpad>/spec-merge-ruleset.json"
```

- [ ] **Step 3: 원본을 지우고 수집이 같은지 본다**

```bash
git rm -q tests/test_check_merge_ruleset.py
uv run ruff check tests/merge_ruleset && uv run ruff format tests/merge_ruleset
uv run pytest tests/merge_ruleset --collect-only -q | tail -3
```

Expected: `58 tests collected` (분할 전 `uv run pytest tests/test_check_merge_ruleset.py --collect-only -q`와 같은 수).

- [ ] **Step 4: 실제로 통과하는지 본다**

```bash
uv run pytest tests/merge_ruleset -q
```

Expected: 58 passed. 실패하면 분할기를 고치고 `git checkout -- tests/ && rm -rf tests/merge_ruleset` 후 Step 2부터 다시.

- [ ] **Step 5: 커밋하지 않는다** — Task 9에서 한 번에 커밋한다. 분할기는 scratchpad에 남긴다.

---

### Task 2: tests를 패키지로 만든다

**Files:**
- Create: `tests/__init__.py` (빈 파일)

**Interfaces:**
- Produces: `tests`가 패키지가 되어 하위 폴더의 basename 충돌이 사라지고 `tests.<pkg>._helpers` import가 성립한다. `pyproject.toml`의 `pythonpath = ["."]`가 저장소 루트를 이미 올려 두므로 추가 설정은 없다.

- [ ] **Step 1: 빈 `tests/__init__.py`를 만든다**

```bash
: > tests/__init__.py
```

- [ ] **Step 2: 평평한 12개가 여전히 걸리는지 본다**

```bash
uv run pytest --collect-only -q | tail -2
```

Expected: 여전히 `1786 tests collected` (Task 1에서 옮긴 58개 포함해 총량 불변).

---

### Task 3: tests/harness_paths — 1157줄 → 6파일

**Files:**
- Create: `tests/harness_paths/` (`__init__.py` · `_helpers.py` · 아래 6개)
- Delete: `tests/test_harness_paths.py`

- [ ] **Step 1: spec을 쓴다**

`<scratchpad>/spec-harness-paths.json`:

```json
[
  {"module": "test_dir_from_command", "anchor": "_Q3"},
  {"module": "test_working_root", "anchor": "_has_git"},
  {"module": "test_masking", "anchor": "test_dir_from_command_reads_past_a_comment_that_holds_an_apostrophe"},
  {"module": "test_invocation_net", "anchor": "NET_INVOCATIONS"},
  {"module": "test_invocation_corpus", "anchor": "RUNS_A_COMMIT"},
  {"module": "test_exemptions", "anchor": "test_a_backtick_pair_balances"}
]
```

- [ ] **Step 2: 분할하고 원본을 지운다**

```bash
uv run python "<scratchpad>/split_tests.py" tests/test_harness_paths.py tests/harness_paths "<scratchpad>/spec-harness-paths.json"
git rm -q tests/test_harness_paths.py
uv run ruff check tests/harness_paths && uv run ruff format tests/harness_paths
```

- [ ] **Step 3: 수집·통과·길이를 본다**

```bash
uv run pytest tests/harness_paths -q | tail -2
wc -l tests/harness_paths/*.py | sort -rn | head -3
```

Expected: 분할 전 `uv run pytest tests/test_harness_paths.py -q`와 같은 수가 passed, 가장 긴 파일이 500줄 이하.

---

### Task 4: tests/harness_scaffold — 1146줄 → 7파일

**Files:**
- Create: `tests/harness_scaffold/`
- Delete: `tests/test_harness_scaffold.py`

- [ ] **Step 1: spec을 쓴다**

`<scratchpad>/spec-harness-scaffold.json`:

```json
[
  {"module": "test_detect", "anchor": "test_detect_state_greenfield"},
  {"module": "test_apply", "anchor": "_write_component"},
  {"module": "test_validate", "anchor": "_baseline_entry"},
  {"module": "test_validate_links", "anchor": "_conv_entry"},
  {"module": "test_cleanup", "anchor": "test_cleanup_removes_research_copies_but_preserves_evidence"},
  {"module": "test_lens", "anchor": "test_lens_marker_id_format"},
  {"module": "test_wiki_id", "anchor": "_wiki_plan"}
]
```

- [ ] **Step 2: 분할하고 원본을 지운다**

```bash
uv run python "<scratchpad>/split_tests.py" tests/test_harness_scaffold.py tests/harness_scaffold "<scratchpad>/spec-harness-scaffold.json"
git rm -q tests/test_harness_scaffold.py
uv run ruff check tests/harness_scaffold && uv run ruff format tests/harness_scaffold
```

- [ ] **Step 3: 수집·통과·길이를 본다**

```bash
uv run pytest tests/harness_scaffold -q | tail -2
wc -l tests/harness_scaffold/*.py | sort -rn | head -3
```

Expected: 분할 전과 같은 수가 passed, 가장 긴 파일이 500줄 이하.

---

### Task 5: tests/skills — 870줄 → 6파일

**Files:**
- Create: `tests/skills/`
- Delete: `tests/test_skills.py`
- Modify: `.claude/rules/skill-frontmatter.md:9` · `CLAUDE.md` (경로 언급)

- [ ] **Step 1: spec을 쓴다**

`<scratchpad>/spec-skills.json`:

```json
[
  {"module": "test_frontmatter", "anchor": "REPO"},
  {"module": "test_bash_rules", "anchor": "bash_rule_matches"},
  {"module": "test_gate_reachability", "anchor": "issued_commands"},
  {"module": "test_links_and_language", "anchor": "test_relative_links_resolve"},
  {"module": "test_shipped_contracts", "anchor": "copy_files"},
  {"module": "test_case_discovery", "anchor": "CASE_DISCOVERY_FILES"}
]
```

- [ ] **Step 2: 분할하고 원본을 지운다**

```bash
uv run python "<scratchpad>/split_tests.py" tests/test_skills.py tests/skills "<scratchpad>/spec-skills.json"
git rm -q tests/test_skills.py
uv run ruff check tests/skills && uv run ruff format tests/skills
```

- [ ] **Step 3: `tests/test_skills.py`를 가리키던 문서를 고친다**

`.claude/rules/skill-frontmatter.md:9`의 `` `tests/test_skills.py` `` → `` `tests/skills/` ``.
`CLAUDE.md`에서 `tests/test_skills.py`를 언급하는 자리도 같은 방식으로. 아래로 확인:

```bash
grep -rn "tests/test_skills\.py" --include="*.md" . | grep -v '^\./\.superpowers/' | grep -v '^\./docs/superpowers/'
```

Expected: 고친 뒤 결과 없음.

- [ ] **Step 4: 수집·통과·길이를 본다**

```bash
uv run pytest tests/skills -q | tail -2
wc -l tests/skills/*.py | sort -rn | head -3
```

Expected: 분할 전과 같은 수가 passed, 가장 긴 파일이 500줄 이하.

---

### Task 6: tests/evals — 2013줄 → 11파일

**Files:**
- Create: `tests/evals/` (`conftest.py`에 autouse 픽스처 `no_real_sessions` · `reset_capture_state`가 간다)
- Delete: `tests/test_evals.py`

**Interfaces:**
- Consumes: 분할기가 `@pytest.fixture`를 `conftest.py`로 보낸다. autouse 픽스처는 패키지 전체에 걸리므로 원본과 같은 범위를 유지한다.
- 주의: `tests/evals`는 최상위 `evals` 패키지와 이름이 같지만, `tests`가 패키지라 `tests.evals`로만 닿는다. 테스트 안의 `import evals.outcome as outcome`은 절대 import라 최상위 `evals`를 계속 가리킨다.

- [ ] **Step 1: spec을 쓴다**

`<scratchpad>/spec-evals.json`:

```json
[
  {"module": "test_cases", "anchor": "REPO"},
  {"module": "test_observe", "anchor": "FIXTURES"},
  {"module": "test_injected_rule", "anchor": "_injected_session_text"},
  {"module": "test_truncation", "anchor": "test_a_spent_turn_cap_cannot_be_ambiguous_at_this_budget"},
  {"module": "test_measure", "anchor": "test_measure_writes_an_entry_the_gate_accepts"},
  {"module": "test_distribution", "anchor": "MANIFESTS"},
  {"module": "test_scores", "anchor": "OK"},
  {"module": "test_capture", "anchor": "test_reduce_capture_keeps_only_the_events_observe_reads"},
  {"module": "test_outcome_golden", "anchor": "test_doc_sync_drift_declares_a_machine_checkable_outcome"},
  {"module": "test_outcome_sha", "anchor": "_CapturingSubprocess"},
  {"module": "test_outcome_run", "anchor": "_DOC_SYNC"}
]
```

- [ ] **Step 2: 분할하고 원본을 지운다**

```bash
uv run python "<scratchpad>/split_tests.py" tests/test_evals.py tests/evals "<scratchpad>/spec-evals.json"
git rm -q tests/test_evals.py
uv run ruff check tests/evals && uv run ruff format tests/evals
```

- [ ] **Step 3: 수집·통과·길이를 본다**

```bash
uv run pytest tests/evals -q | tail -2
wc -l tests/evals/*.py | sort -rn | head -3
```

Expected: 분할 전과 같은 수가 passed, 가장 긴 파일이 500줄 이하. autouse 픽스처가 옮겨졌는지는
`test_the_suite_cannot_spawn_a_real_session`이 통과하는 것으로 확인된다 — 그 픽스처가 빠지면
그 테스트가 먼저 깨진다.

---

### Task 7: tests/flow_gate — 2315줄 → 12파일

**Files:**
- Create: `tests/flow_gate/`
- Delete: `tests/test_flow_gate_check.py`
- Modify: `CLAUDE.md` (`tests/test_flow_gate_check.py` 언급)

- [ ] **Step 1: spec을 쓴다**

`<scratchpad>/spec-flow-gate.json`:

```json
[
  {"module": "test_policy_and_main", "anchor": "test_lifecycle_branches_from_config"},
  {"module": "test_module_commands", "anchor": "_MODCFG"},
  {"module": "test_classify", "anchor": "_git_ok"},
  {"module": "test_runner_commit", "anchor": "_repo_bash"},
  {"module": "test_runner_merge", "anchor": "test_runner_merge_gate_survives_clean_tree"},
  {"module": "test_module_checks", "anchor": "test_parse_check_plain_string_is_every_commit"},
  {"module": "test_merge_strategy", "anchor": "test_merge_strategy_loads_rules"},
  {"module": "test_merge_check", "anchor": "_write_policy"},
  {"module": "test_wiki_gate", "anchor": "_wiki_host"},
  {"module": "test_doc_style_gate", "anchor": "_doc_style_host"},
  {"module": "test_gate_in_process", "anchor": "_classify_docs"},
  {"module": "test_merge_parsing_edges", "anchor": "test_merge_parsing_anchors_on_the_git_that_owns_the_subcommand"}
]
```

- [ ] **Step 2: 분할하고 원본을 지운다**

```bash
uv run python "<scratchpad>/split_tests.py" tests/test_flow_gate_check.py tests/flow_gate "<scratchpad>/spec-flow-gate.json"
git rm -q tests/test_flow_gate_check.py
uv run ruff check tests/flow_gate && uv run ruff format tests/flow_gate
```

- [ ] **Step 3: CLAUDE.md의 단일 파일 실행 예시를 고친다**

CLAUDE.md Commands의 `uv run pytest tests/test_flow_gate_check.py::<name>` →
`uv run pytest tests/flow_gate/test_merge_check.py::<name>`.

- [ ] **Step 4: 수집·통과·길이를 본다**

```bash
uv run pytest tests/flow_gate -q | tail -2
wc -l tests/flow_gate/*.py | sort -rn | head -3
```

Expected: 분할 전과 같은 수가 passed, 가장 긴 파일이 500줄 이하.

---

### Task 8: tests/wiki_graph · tests/flow_init — 남은 두 개

**Files:**
- Create: `tests/wiki_graph/` · `tests/flow_init/`
- Delete: `tests/test_wiki_graph.py` · `tests/test_flow_init_setup.py`

- [ ] **Step 1: wiki_graph spec을 쓴다**

`<scratchpad>/spec-wiki-graph.json`:

```json
[
  {"module": "test_config_and_front_matter", "anchor": "_write_config"},
  {"module": "test_collect_nodes", "anchor": "test_duplicate_wiki_id_lines_warn"},
  {"module": "test_validate_structure", "anchor": "_mk"},
  {"module": "test_warnings", "anchor": "test_adjacency_ignores_direction"},
  {"module": "test_neighbors", "anchor": "_wiki_repo"},
  {"module": "test_build", "anchor": "test_build_writes_graph_and_verify_passes"},
  {"module": "test_verify", "anchor": "test_coerced_id_is_reported_instead_of_vanishing"},
  {"module": "test_stale", "anchor": "_git_repo_with_source"},
  {"module": "test_stamps", "anchor": "_stamp_repo"},
  {"module": "test_stamps_renames", "anchor": "_renamed_nodes_repo"},
  {"module": "test_nodes_for", "anchor": "_nodes_for_repo"},
  {"module": "test_structural_caps", "anchor": "test_broken_front_matter_with_marker_blocks_and_names_the_file"},
  {"module": "test_derive_id", "anchor": "_EXAMPLES"},
  {"module": "test_wiki_init_parity", "anchor": "_REPO"}
]
```

- [ ] **Step 2: flow_init spec을 쓴다**

`<scratchpad>/spec-flow-init.json`:

```json
[
  {"module": "test_gate_registration", "anchor": "test_register_gate_creates"},
  {"module": "test_copy_and_uninstall", "anchor": "test_copy_artifacts_includes_shared_helper"},
  {"module": "test_render_workflows", "anchor": "_write_flow_config"},
  {"module": "test_config_slots", "anchor": "_mk_example"},
  {"module": "test_render_versioning", "anchor": "test_render_versioning_python"},
  {"module": "test_render_unit_test", "anchor": "_write_unit_test_config"},
  {"module": "test_workflow_contexts", "anchor": "WORKFLOW_CONTEXTS"},
  {"module": "test_hook_matcher", "anchor": "test_the_gate_answerer_is_copied_before_the_runner_that_asks_it"},
  {"module": "test_settings_shapes", "anchor": "test_uninstall_leaves_a_host_hook_that_shares_the_gate_entry"},
  {"module": "test_settings_writes", "anchor": "test_uninstall_leaves_a_hook_of_the_hosts_that_shares_the_script_name"},
  {"module": "test_setup_verdict", "anchor": "test_the_gate_command_resolves_against_the_host"},
  {"module": "test_copied_script_guards", "anchor": "_is_type_checking"}
]
```

- [ ] **Step 3: 둘 다 분할하고 원본을 지운다**

```bash
uv run python "<scratchpad>/split_tests.py" tests/test_wiki_graph.py tests/wiki_graph "<scratchpad>/spec-wiki-graph.json"
uv run python "<scratchpad>/split_tests.py" tests/test_flow_init_setup.py tests/flow_init "<scratchpad>/spec-flow-init.json"
git rm -q tests/test_wiki_graph.py tests/test_flow_init_setup.py
uv run ruff check tests/wiki_graph tests/flow_init && uv run ruff format tests/wiki_graph tests/flow_init
```

- [ ] **Step 4: 수집·통과·길이를 본다**

```bash
uv run pytest tests/wiki_graph tests/flow_init -q | tail -2
wc -l tests/wiki_graph/*.py tests/flow_init/*.py | sort -rn | head -5
```

Expected: 분할 전과 같은 수가 passed, 가장 긴 파일이 500줄 이하. 500줄을 넘는 파일이 남으면
그 파일의 spec 항목을 anchor 하나로 더 쪼개고 Step 3을 다시 돌린다.

---

### Task 9: 규칙을 CLAUDE.md에 못박고 전체를 검증한 뒤 커밋

**Files:**
- Modify: `CLAUDE.md` (Conventions에 규칙 한 줄 · Folder structure의 `tests/` 항목)

- [ ] **Step 1: Conventions에 규칙을 넣는다**

`CLAUDE.md`의 Conventions 목록에 아래를 추가한다 — "코드가 말할 수 없는 것만 쓴다"에 맞춰
기준과 그 기준을 둔 이유만 남긴다.

```markdown
- **A test file past 500 lines becomes a folder** — `tests/<module under test>/`, mirroring
  `scripts/`·`evals/`, with every file inside under 500 lines: shared symbols in `_helpers.py`,
  fixtures in `conftest.py`, the package's own `__init__.py`. The `__init__.py` is what lets two
  folders both hold a `test_build.py` — without it pytest reads the second as a re-import of the
  first and refuses to collect. Files still under the cap stay flat at `tests/`.
```

- [ ] **Step 2: Folder structure의 tests/ 항목을 고친다**

기존 줄:

```text
tests/           pytest over scripts/ · test_skills.py (skill FILES: frontmatter/links/refs + the git
                 commands skills and rules/ issue vs the gate's invocation grammar) · test_evals.py (model-free half of evals/)
```

새 줄:

```text
tests/           pytest over scripts/ — a module past 500 lines is a package of its own (skills/: skill
                 FILES incl. the git commands skills and rules/ issue vs the gate's invocation grammar ·
                 evals/: model-free half of evals/) and the rest stay flat
```

- [ ] **Step 3: 산문 린트를 통과하는지 본다**

```bash
uv run python scripts/doc_style_check.py --root . --lint CLAUDE.md .claude/rules/skill-frontmatter.md
```

Expected: 위반 없음.

- [ ] **Step 4: node id 집합이 분할 전과 같은지 본다**

```bash
uv run pytest --collect-only -q 2>/dev/null | grep '::' | sed 's/.*:://' | sort > "<scratchpad>/after.txt"
diff "<scratchpad>/before.txt" "<scratchpad>/after.txt" && echo "SAME TESTS"
wc -l < "<scratchpad>/after.txt"
```

Expected: `SAME TESTS`, 그리고 1786.

- [ ] **Step 5: 전체를 돌린다**

```bash
uv run pytest -q 2>&1 | tail -3
uv run ruff check && uv run ruff format --check
uv run pre-commit run --all-files
```

Expected: 분할 전 기준선과 같은 수가 passed, 린트·포맷·pre-commit 모두 통과.
(전체 스위트는 10분을 넘는다 — 백그라운드로 돌리고 기다린다.)

- [ ] **Step 6: 500줄 초과가 남아 있지 않은지 본다**

```bash
find tests -name '*.py' | xargs wc -l | sort -rn | head -5
```

Expected: 가장 긴 파일이 500줄 이하.

- [ ] **Step 7: `commit` 스킬로 커밋한다**

`Skill: commit` — tier `dev`, 내용은 "500줄 넘는 테스트 모듈을 대상 모듈 이름의 패키지로 쪼개고
그 기준을 CLAUDE.md에 못박음". 타입은 `test:` (소비자에게 나가는 `.md`가 아니라 저장소 자신의
CLAUDE.md와 테스트만 움직인다). 분할기(scratchpad)는 스테이징하지 않는다.
