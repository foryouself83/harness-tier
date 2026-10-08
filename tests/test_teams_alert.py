import json
import subprocess
import sys
from pathlib import Path

import scripts._harness_paths as vp
import scripts.teams_alert as ta
from tests._non_utf8 import ansi_locale_env, cp949_stdio_env
from tests.flow_gate._helpers import _init_repo, _rg, requires_git

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "teams_alert.py"


def test_host_root_is_shared_helper():
    # _host_root is a backward-compatible alias of the shared host_root. The SSOT of the
    # fallback logic (env → git toplevel → .claude marker → cwd) is _harness_paths, and
    # test_harness_paths verifies the behavior.
    assert ta._host_root is vp.host_root


def test_host_root_prefers_env(monkeypatch, tmp_path: Path):
    # verify the alias links to the shared helper and honors env.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert ta._host_root() == tmp_path.resolve()


def test_set_and_resolve_webhook(monkeypatch, tmp_path: Path):
    # separate storage of local (personal) and tracked (branch) files + merged resolution
    # + push-channel exclusion
    tracked = tmp_path / "teams-webhooks.json"
    local = tmp_path / ".teams-webhooks.local.json"
    monkeypatch.setattr(ta, "TRACKED_FILE", tracked)
    monkeypatch.setattr(ta, "LOCAL_FILE", local)

    assert ta.set_webhook("personal", "https://x") == local  # personal → local file
    assert ta.set_webhook("dev", "https://y") == local  # a branch URL stays out of git
    assert ta.set_webhook("main", "https://z", shared=True) == tracked
    assert ta.resolve_webhook("personal") == "https://x"
    assert ta.resolve_webhook("dev") == "https://y"
    assert ta.resolve_webhook("main") == "https://z"
    assert ta.resolve_webhook("absent") is None
    # The tracked file names the watched branch for every clone, never its `sig=` URL.
    assert json.loads(tracked.read_text(encoding="utf-8")) == {"dev": "", "main": "https://z"}
    assert ta.push_channels() == ["dev", "main"]  # personal (local-only) is never a push target


def test_a_local_only_branch_is_still_a_push_target(monkeypatch, tmp_path: Path):
    """A clone whose tracked file predates the branch still posts for the URL it holds."""
    monkeypatch.setattr(ta, "TRACKED_FILE", tmp_path / "teams-webhooks.json")
    local = tmp_path / ".teams-webhooks.local.json"
    monkeypatch.setattr(ta, "LOCAL_FILE", local)
    local.write_text('{"personal": "https://x", "stage": "https://s"}', encoding="utf-8")
    assert ta.push_channels() == ["stage"]


def test_setting_a_branch_locally_keeps_a_teammates_tracked_url(monkeypatch, tmp_path: Path):
    tracked = tmp_path / "teams-webhooks.json"
    monkeypatch.setattr(ta, "TRACKED_FILE", tracked)
    monkeypatch.setattr(ta, "LOCAL_FILE", tmp_path / ".teams-webhooks.local.json")
    tracked.write_text('{"dev": "https://team"}', encoding="utf-8")
    ta.set_webhook("dev", "https://mine")
    assert json.loads(tracked.read_text(encoding="utf-8")) == {"dev": "https://team"}
    assert ta.resolve_webhook("dev") == "https://mine"


def test_the_cli_names_the_url_that_still_wins(tmp_path: Path):
    """Registering one side while the other side still holds a URL leaves two copies; the CLI
    says which one is left, since only the local one stays out of git."""
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)

    def cli(*args: str) -> str:
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--set", *args],
            env=cp949_stdio_env(CLAUDE_PROJECT_DIR=str(tmp_path)),
            capture_output=True,
        )
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        return r.stdout.decode("utf-8")

    assert "teams-webhooks.json" in cli("dev", "https://team", "--shared")
    assert "아직 남아" in cli("dev", "https://mine")
    assert "우선합니다" in cli("dev", "https://team2", "--shared")
    tracked = json.loads((cfg / "teams-webhooks.json").read_text(encoding="utf-8"))
    assert tracked == {"dev": "https://team2"}


def test_set_confirms_in_utf8_on_a_cp949_host(tmp_path: Path):
    # Invariant #2. /flow-init runs --set through a pipe, where stdout takes the locale codec,
    # and the confirmation is Korean: garbled on a cp949 host, a crash on a cp1252 one.
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--set", "personal", "https://example.invalid/hook"],
        env=cp949_stdio_env(CLAUDE_PROJECT_DIR=str(tmp_path)),
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "등록됨".encode() in r.stdout


@requires_git
def test_context_label_reads_a_korean_branch_without_utf8_mode(tmp_path: Path):
    # Invariant #2. The Notification hook and pre-push run this without PYTHONUTF8, and the
    # branch reaches the Teams card through a pipe the locale codec decodes.
    _init_repo(tmp_path)
    _rg(["switch", "-q", "-c", "feature/한글"], tmp_path)
    code = "import json, scripts.teams_alert as t; print(json.dumps(t._context_label()))"
    r = subprocess.run(
        [sys.executable, "-c", code],
        env=ansi_locale_env(PYTHONPATH=str(REPO), CLAUDE_PROJECT_DIR=str(tmp_path)),
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert json.loads(r.stdout).endswith(" @ feature/한글")
