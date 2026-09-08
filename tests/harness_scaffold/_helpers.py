from pathlib import Path

import scripts.harness_scaffold as hs


def _write_component(path: Path, name: str, desc: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\nbody\n", encoding="utf-8")


def _baseline_entry(extra_body=""):
    anchors = "".join(
        f"<!-- rule:{k} -->\n"
        for k in ("karpathy", "dry-constants", "version-pinning", "security", "reuse-first")
    )
    return {
        "path": "CLAUDE.md",
        "action": "marker_upsert",
        "marker_id": "harness:baseline",
        "content": anchors + extra_body,
    }


def _linking_plan(target_content, link):
    return {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds/README.md", "action": "create", "content": f"[FR]({link})"},
            {"path": "docs/srs/README.md", "action": "create", "content": target_content},
        ]
    }


def _anchor_issues(tmp_path, target_content, link):
    rep = hs.validate_plan(tmp_path, _linking_plan(target_content, link))
    return [i for i in rep["issues"] if i["kind"] == "dead-anchor"]
