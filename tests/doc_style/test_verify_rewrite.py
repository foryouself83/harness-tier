"""`--verify-git`: a rewrite has to keep everything the prose carried."""

import subprocess
from pathlib import Path

from tests.doc_style._helpers import (
    git_head_text,
    main,
    strip_prose,
    verify,
)

# ---------- What --verify proves ----------


BEFORE_MD = """# Title

Some long explanatory paragraph that will be compressed.

- one
- two
- three

See https://example.com/spec and the `--verify` flag.

```bash
python3 scripts/doc_style_check.py --lint
```
"""


def test_a_faithful_rewrite_verifies_clean():
    after = BEFORE_MD.replace(
        "Some long explanatory paragraph that will be compressed.", "Compressed."
    )
    assert verify(Path("d.md"), BEFORE_MD, after) == []


def test_a_lost_heading_is_an_error():
    after = BEFORE_MD.replace("# Title\n", "")
    assert "HEADING" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_an_edited_code_block_is_an_error():
    after = BEFORE_MD.replace("--lint", "--lint --root .")
    assert "CODE" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_a_lost_url_is_an_error():
    after = BEFORE_MD.replace("https://example.com/spec", "the spec")
    assert "URL" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_a_lost_inline_code_span_is_an_error():
    after = BEFORE_MD.replace("`--verify`", "verify")
    assert "INLINE" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_dropped_bullets_warn():
    after = BEFORE_MD.replace("- two\n- three\n", "")
    findings = verify(Path("d.md"), BEFORE_MD, after)
    assert ("BULLET", "warning") in {(code, level) for level, _, code, _ in findings}
    assert not [f for f in findings if f[0] == "error" and f[2] == "BULLET"]


# ---------- Source: prose may move, code may not ----------


PY_BEFORE = '''"""Long docstring that used to explain the whole history."""

import os


def f(a, b=2):  # a comment nobody needs
    """Explains what the next line already says."""
    return os.path.join(str(a), str(b))
'''


def test_a_comment_only_rewrite_verifies_clean():
    after = '''"""One line."""

import os


def f(a, b=2):
    """Join a and b."""
    return os.path.join(str(a), str(b))
'''
    assert verify(Path("m.py"), PY_BEFORE, after) == []


def test_a_code_change_under_a_prose_rewrite_is_an_error():
    after = PY_BEFORE.replace("b=2", "b=3")
    assert "CODE" in [code for _, _, code, _ in verify(Path("m.py"), PY_BEFORE, after)]


def test_reindenting_prose_does_not_change_the_code_view():
    assert strip_prose(Path("m.py"), PY_BEFORE) == strip_prose(
        Path("m.py"), PY_BEFORE.replace("# a comment nobody needs", "")
    )


def test_shell_trailing_comment_is_prose_not_code():
    before = "set -e\nrun --now   # this used to be optional\n"
    after = "set -e\nrun --now\n"
    assert verify(Path("s.sh"), before, after) == []


def test_shell_hash_inside_quotes_is_code():
    # `# b` sits inside a quoted string: code, never a trailing comment. Assert on the
    # stripped code, since a non-empty verify() also holds with the quote handling gone —
    # the two files differ either way.
    before = "echo 'a # b'\n"
    assert strip_prose(Path("s.sh"), before) == "echo 'a # b'"
    assert verify(Path("s.sh"), before, "echo 'a'\n")


def test_verify_git_compares_against_head(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    doc = tmp_path / "d.md"
    doc.write_text(BEFORE_MD, encoding="utf-8")
    subprocess.run(["git", "add", "d.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp_path, check=True)

    doc.write_text(BEFORE_MD.replace("# Title\n", ""), encoding="utf-8")
    assert main(["--root", str(tmp_path), "--verify-git", str(doc)]) == 1


def test_verify_git_ignores_a_file_head_never_had(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    doc = tmp_path / "new.md"
    doc.write_text("It used to work.\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "--verify-git", str(doc)]) == 0


def test_git_head_text_answers_none_outside_the_repo(tmp_path: Path):
    # doc-sync passes user-supplied paths to --verify-git; an outside one must not traceback.
    outside = tmp_path.parent / "not-in-this-repo.md"
    assert git_head_text(tmp_path, outside) is None
