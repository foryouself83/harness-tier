from pathlib import Path

import scripts._harness_paths as vp
import scripts.teams_alert as ta


def test_host_root_is_shared_helper():
    # _host_root is a backward-compatible alias of the shared host_root. The SSOT of the
    # fallback logic (env → git toplevel → .claude marker → cwd) is _harness_paths, and
    # test_harness_paths verifies the behavior.
    assert ta._host_root is vp.host_root


def test_host_root_prefers_env(monkeypatch, tmp_path: Path):
    # verify the alias actually links to the shared helper and honors env.
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
    assert ta.set_webhook("dev", "https://y") == tracked  # branch → tracked file
    assert ta.resolve_webhook("personal") == "https://x"
    assert ta.resolve_webhook("dev") == "https://y"
    assert ta.resolve_webhook("absent") is None
    assert ta.push_channels() == ["dev"]  # personal (local-only) is excluded from push targets
