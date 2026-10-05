"""A session started below the git top level, where GitHub and pre-commit look for nothing."""

from scripts.flow_init_setup import subdir_warning
from tests.flow_gate._helpers import _init_repo, requires_git


@requires_git
def test_a_subdirectory_host_is_warned(tmp_path):
    _init_repo(tmp_path / "repo")
    sub = tmp_path / "repo" / "services" / "api"
    sub.mkdir(parents=True)
    (line,) = subdir_warning(sub)
    assert ".github/workflows/" in line and ".pre-commit-config.yaml" in line


@requires_git
def test_the_top_level_and_a_plain_directory_are_not(tmp_path):
    _init_repo(tmp_path / "repo")
    assert subdir_warning(tmp_path / "repo") == []
    (tmp_path / "plain").mkdir()
    assert subdir_warning(tmp_path / "plain") == []
