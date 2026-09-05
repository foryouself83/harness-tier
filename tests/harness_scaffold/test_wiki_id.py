from pathlib import Path

import scripts.harness_scaffold as hs

# ---------------------------------------------------------------- wiki-id parity


def _wiki_plan(path: str, content: str) -> dict:
    return {"files": [{"path": path, "action": "create", "content": content}]}


def test_validate_plan_flags_hand_derived_wiki_id(tmp_path):
    # A hand-derived id that disagrees with the mechanical one comes back later as a
    # duplicate or a format failure, and --verify then blocks every commit. Plan time is
    # the only point that catches it.
    content = "---\nwiki_id: code-style-python\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/code-style/python.md", content))
    hits = [i for i in res["issues"] if i["kind"] == "wiki-id"]
    assert hits and "code-style.python" in hits[0]["detail"]


def test_validate_plan_accepts_the_derived_wiki_id(tmp_path):
    content = "---\nwiki_id: code-style.python\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/code-style/python.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_exempts_defect_ids_from_path_parity(tmp_path):
    # A defect document's wiki_id follows defect-template's `defect.<slug>` convention
    # (stated in wiki-init §5), not path derivation, so the parity check must not raise a
    # high on it.
    content = "---\nwiki_id: defect.login-timeout\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/defects/login-timeout.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_flags_unfilled_id_placeholder(tmp_path):
    # A template copied without filling {{ID}} in trips the same check.
    content = "---\nwiki_id: '{{ID}}'\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/sds/README.md", content))
    assert any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_ignores_md_outside_wiki_root(tmp_path):
    content = "---\nwiki_id: totally-wrong\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan(".claude/rules/x-conventions.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_ignores_docs_without_wiki_id(tmp_path):
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/guide.md", "본문만\n"))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_flags_boolean_wiki_id(tmp_path):
    # YAML 1.1: an unquoted `no` resolves to the bool False, not the string "no". Left
    # unflagged this reads as "no wiki_id" and the parity check silently never runs.
    content = "---\nwiki_id: no\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/guide.md", content))
    hits = [i for i in res["issues"] if i["kind"] == "wiki-id"]
    assert hits and "bool" in hits[0]["detail"]


def test_validate_plan_flags_numeric_wiki_id(tmp_path):
    # YAML 1.1: an unquoted leading-zero scalar resolves to an (octal) int, not a string.
    content = "---\nwiki_id: 0123456\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/guide.md", content))
    hits = [i for i in res["issues"] if i["kind"] == "wiki-id"]
    assert hits and "int" in hits[0]["detail"]


def test_validate_plan_skips_front_matter_not_at_byte_zero(tmp_path):
    # A leading HTML comment marks the document as outside the wiki, the same semantics
    # wiki_graph reads: not a node, so it is skipped.
    content = "<!-- note -->\n---\nwiki_id: wrong\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/guide.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_flags_underivable_path(tmp_path):
    content = "---\nwiki_id: onboarding\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/온보딩.md", content))
    assert any(i["kind"] == "wiki-id" for i in res["issues"])


def _write_wiki_config(root: Path, body: str) -> None:
    cfg = root / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "flow-config.yaml").write_text(body, encoding="utf-8")


def test_validate_plan_treats_docs_old_as_outside_the_docs_root(tmp_path):
    # `rel.startswith(f"{wiki_root}/")` requires the separator — weakening it to
    # `rel.startswith(wiki_root)` (no "/") would false-match "docs-old/a.md" against root
    # "docs" (the same path-prefix footgun Invariant #6 guards against for worktree
    # identity), running the parity check on a file that was never under the wiki root.
    content = "---\nwiki_id: totally-wrong\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs-old/a.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_treats_dot_wiki_root_as_every_md(tmp_path):
    # A host may configure the repo root itself as the wiki root. _wiki_root_hint then
    # returns "." (not ""), and `rel.startswith(f"{wiki_root}/")` would never match since
    # rel is normalized and never carries a leading "./" — silently skipping every file.
    # A root of "." must instead mean every .md in the plan is under the wiki root.
    _write_wiki_config(tmp_path, "wiki:\n  root: .\n")
    content = "---\nwiki_id: totally-wrong\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("guide.md", content))
    hits = [i for i in res["issues"] if i["kind"] == "wiki-id"]
    assert hits and "guide" in hits[0]["detail"]
