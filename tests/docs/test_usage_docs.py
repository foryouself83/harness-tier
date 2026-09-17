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


def test_the_topic_list_is_the_directory():
    """A topic added on disk but not here is never checked for a twin or an index entry."""
    on_disk = {
        p.name.removesuffix(".md").removesuffix(".ko") for p in USAGE_DIR.glob("*.md")
    }
    assert on_disk == set(TOPICS)


@pytest.mark.parametrize("topic", TOPICS)
def test_every_topic_has_both_languages(topic: str):
    assert (USAGE_DIR / f"{topic}.md").is_file(), f"docs/usage/{topic}.md is missing"
    assert (USAGE_DIR / f"{topic}.ko.md").is_file(), f"docs/usage/{topic}.ko.md is missing"


@pytest.mark.parametrize(("index", "suffix"), [("USAGE.md", ".md"), ("USAGE.ko.md", ".ko.md")])
def test_the_index_links_every_topic_in_its_language(index: str, suffix: str):
    text = (ROOT / index).read_text(encoding="utf-8")
    missing = [t for t in TOPICS if f"docs/usage/{t}{suffix})" not in text]
    assert not missing, f"{index} does not link {missing}"


def _docs() -> list[Path]:
    top = [ROOT / name for name in ("README.md", "README.ko.md", "USAGE.md", "USAGE.ko.md")]
    return top + sorted(USAGE_DIR.glob("*.md"))


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
        elif frag and dest.suffix == ".md":
            if not _has_anchor(dest.read_text(encoding="utf-8"), frag):
                broken.append(target)
    assert not broken, f"{doc.relative_to(ROOT).as_posix()} links to nothing at {broken}"
