from pathlib import Path

import scripts._vway_paths as vp
import scripts.teams_alert as ta


def test_host_root_is_shared_helper():
    # _host_root 는 공용 host_root 의 하위호환 alias 다. 폴백 로직(env → git toplevel →
    # .claude 마커 → cwd)의 SSOT 는 _vway_paths 이고 동작 검증은 test_vway_paths 가 한다.
    assert ta._host_root is vp.host_root


def test_host_root_prefers_env(monkeypatch, tmp_path: Path):
    # alias 가 실제로 공용 헬퍼로 연결돼 env 를 존중하는지 확인.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert ta._host_root() == tmp_path.resolve()


def test_set_and_resolve_webhook(monkeypatch, tmp_path: Path):
    # local(personal) 과 tracked(브랜치) 파일 분리 저장 + 병합 해석 + push 채널 제외
    tracked = tmp_path / "teams-webhooks.json"
    local = tmp_path / ".teams-webhooks.local.json"
    monkeypatch.setattr(ta, "TRACKED_FILE", tracked)
    monkeypatch.setattr(ta, "LOCAL_FILE", local)

    assert ta.set_webhook("personal", "https://x") == local  # personal → local 파일
    assert ta.set_webhook("dev", "https://y") == tracked  # 브랜치 → tracked 파일
    assert ta.resolve_webhook("personal") == "https://x"
    assert ta.resolve_webhook("dev") == "https://y"
    assert ta.resolve_webhook("absent") is None
    assert ta.push_channels() == ["dev"]  # personal(local 전용)은 push 대상 제외
