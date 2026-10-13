"""The plugin-only tree consumers install (`.github/scripts/plugin_dist.py`): everything a
session, /flow-init or a skill reaches is in it, nothing dev-only is, and it fits the limits
Anthropic's and OpenAI's plugin directories check."""

from __future__ import annotations

import importlib.util
import json
import re
import struct
import zipfile
from pathlib import Path

import pytest

import scripts.flow_init_setup as fis

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "plugin_dist", REPO / ".github/scripts/plugin_dist.py"
)
pd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pd)

SHA = "0123456789abcdef0123456789abcdef01234567"
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


@pytest.fixture(scope="module")
def dist(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dist") / "plugin"
    pd.build(REPO, out)
    return out


@pytest.fixture(scope="module")
def codex_names(dist, tmp_path_factory) -> list[str]:
    return pd.codex_zip(dist, tmp_path_factory.mktemp("zip") / "codex.zip")


def _files(dist: Path) -> list[Path]:
    return [p for p in dist.rglob("*") if p.is_file()]


@pytest.mark.parametrize(
    "rel",
    [
        "tests",
        "evals",
        ".github",
        "graft",
        ".claude",
        "docs/superpowers",
        "docs/plugins",
        "CHANGELOG.md",
        "pyproject.toml",
        "uv.lock",
        "ruff.toml",
        "scripts/skill_sandbox.py",
    ],
)
def test_dev_only_paths_stay_out(dist, rel):
    assert not (dist / rel).exists(), rel


def test_every_plugin_root_reference_resolves(dist):
    """A hook, skill or script naming `${CLAUDE_PLUGIN_ROOT}/<path>` reads it from this tree."""
    pattern = re.compile(r"\$\{?(?:CLAUDE_PLUGIN_ROOT|PLUGIN_ROOT)\}?/([\w./-]+)")
    missing = set()
    for path in _files(dist):
        if path.suffix not in {".md", ".sh", ".json", ".py", ".cmd", ".yml", ".yaml"}:
            continue
        for rel in pattern.findall(path.read_text(encoding="utf-8", errors="replace")):
            rel = rel.rstrip(".")
            if "<" in rel or "*" in rel or rel.endswith("/"):
                continue
            if not (dist / rel).exists():
                missing.add(f"{path.relative_to(dist).as_posix()} -> {rel}")
    assert not missing, sorted(missing)


def test_flow_init_finds_every_source_it_copies(dist):
    rels = [
        *fis.COPY_FILES,
        fis.TIERS_FILENAME,
        fis.EXAMPLE_CONFIG,
        "pre-commit-hooks.example.yaml",
        *(rel for rels in fis.HARNESS_COPY_FILES.values() for rel in rels),
        *(rel for rels in fis.HARNESS_ROOT_FILES.values() for rel in rels),
        *(rel for rels in fis.HARNESS_ROOT_DIRS.values() for rel in rels),
    ]
    assert [rel for rel in rels if not (dist / rel).exists()] == []
    source = (REPO / "scripts/flow_init_setup.py").read_text(encoding="utf-8")
    templates = set(re.findall(r"github/[\w.-]+\.workflow\.example\.yml", source))
    assert templates and [t for t in templates if not (dist / t).is_file()] == []
    assert (dist / "templates/design-docs").is_dir()


def test_manifest_paths_resolve(dist):
    claude = json.loads((dist / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((dist / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    for rel in (
        claude["icon"],
        claude["hooks"],
        codex["skills"],
        *[codex["interface"][k] for k in ("logo", "composerIcon")],
    ):
        assert (dist / rel).exists(), rel


def test_the_tree_fits_the_directory_limits(dist):
    files = _files(dist)
    assert len(files) <= 512
    big = [p.name for p in files if p.suffix not in IMAGES and p.stat().st_size > 256 * 1024]
    assert big == []
    assert not [p for p in files if p.name in {".DS_Store", "Thumbs.db", "desktop.ini"}]
    readme = re.sub(r"```.*?```", "", (dist / "README.md").read_text(encoding="utf-8"), flags=re.S)
    assert len(readme.split()) >= 40
    assert (dist / "LICENSE").is_file()


def test_icon_is_a_square_png_both_directories_accept(dist):
    icon = dist / "assets/icon.png"
    head = icon.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", head[16:24])
    assert width == height and 512 <= width <= 2048
    assert icon.stat().st_size < 2 * 1024 * 1024


def test_the_branch_is_its_own_marketplace(dist):
    claude = json.loads((dist / pd.CLAUDE_MARKET).read_text(encoding="utf-8"))
    codex = json.loads((dist / pd.CODEX_MARKET).read_text(encoding="utf-8"))
    assert claude["plugins"][0]["source"] == "./"
    assert codex["plugins"][0]["source"] == {"source": "local", "path": "./"}
    assert not (dist / "plugin.json").exists(), "a root plugin.json switches Codex's loader"


def test_codex_package_carries_no_lifecycle_hooks(dist, codex_names):
    assert not [n for n in codex_names if n.endswith("hooks.json")]
    assert not [n for n in codex_names if n.startswith((".claude-plugin/", ".agents/"))]
    assert ".codex-plugin/plugin.json" in codex_names and "assets/icon.png" in codex_names
    codex = json.loads((dist / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    assert "hooks" not in codex
    # /flow-init copies the session hooks into the host from here.
    for rel in fis.HARNESS_ROOT_FILES["codex"]:
        assert rel in codex_names, rel


def test_codex_zip_holds_what_it_lists(dist, tmp_path):
    zip_path = tmp_path / "c.zip"
    names = pd.codex_zip(dist, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert sorted(zf.namelist()) == names


def _markets(root: Path) -> None:
    for rel in (pd.CLAUDE_MARKET, pd.CODEX_MARKET):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes((REPO / rel).read_bytes())


def test_pin_points_both_marketplaces_at_the_plugin_branch(tmp_path):
    _markets(tmp_path)
    pd.pin(tmp_path, SHA)
    claude = json.loads((tmp_path / pd.CLAUDE_MARKET).read_text(encoding="utf-8"))
    codex = json.loads((tmp_path / pd.CODEX_MARKET).read_text(encoding="utf-8"))
    assert claude["plugins"][0]["source"] == {
        "source": "github",
        "repo": pd.REPO,
        "ref": "plugin",
        "sha": SHA,
    }
    assert codex["plugins"][0]["source"] == {
        "source": "url",
        "url": pd.GIT_URL,
        "ref": "plugin",
        "sha": SHA,
    }
    # Everything but the source survives.
    before = json.loads((REPO / pd.CODEX_MARKET).read_text(encoding="utf-8"))
    assert codex["plugins"][0]["policy"] == before["plugins"][0]["policy"]


@pytest.mark.parametrize("bad", ["abc", SHA.upper(), SHA[:-1] + "g"])
def test_pin_refuses_anything_but_a_full_sha(tmp_path, bad):
    _markets(tmp_path)
    with pytest.raises(SystemExit):
        pd.pin(tmp_path, bad)


def test_committed_marketplaces_name_a_fetchable_commit():
    """Before the first plugin-branch release they still name a main commit with no `ref`;
    after it, the `plugin` branch. A `ref` naming a branch that does not exist yet would
    break every install in between."""
    claude = json.loads((REPO / pd.CLAUDE_MARKET).read_text(encoding="utf-8"))["plugins"][0]
    codex = json.loads((REPO / pd.CODEX_MARKET).read_text(encoding="utf-8"))["plugins"][0]
    src = claude["source"]
    assert src["source"] == "github" and src["repo"] == pd.REPO
    assert re.fullmatch(r"[0-9a-f]{40}", src["sha"]) and src.get("ref") in (None, "plugin")
    # The same commit for both harnesses, through a git source Codex can fetch by sha.
    assert codex["source"] == {
        "source": "url",
        "url": pd.GIT_URL,
        "ref": src.get("ref", "main"),
        "sha": src["sha"],
    }


def test_main_release_publishes_the_branch_before_pinning_it():
    text = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    build = text.index("plugin_dist.py build")
    pin = text.index("plugin_dist.py pin")
    assert build < pin < text.index("gh release upload")
    assert "pin-marketplace-sha" not in text
    assert "git add .claude-plugin/marketplace.json .agents/plugins/marketplace.json" in text


def test_an_unreadable_plugin_branch_never_starts_a_new_history():
    text = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "2) git worktree add --orphan -b plugin" in text
    assert re.search(r"\*\) echo \"::error::cannot read origin's plugin branch.*exit 1", text)


def test_consumer_docs_link_only_to_files_the_tree_carries(dist):
    link = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
    pages = [*dist.glob("README*.md"), *dist.glob("USAGE*.md"), *(dist / "docs/usage").glob("*.md")]
    broken = [
        f"{page.relative_to(dist).as_posix()} -> {target}"
        for page in pages
        for target in link.findall(page.read_text(encoding="utf-8"))
        if "://" not in target
        and not target.startswith("mailto:")
        and not (page.parent / target).exists()
    ]
    assert broken == []
