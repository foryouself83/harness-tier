import json

import scripts.harness_insight as hi

# --- normalize_cmd: generic command grouping (no per-project command list) ---


def test_normalize_cmd_basename_only():
    assert hi.normalize_cmd("/usr/bin/python3 foo.py") == "python3"


def test_normalize_cmd_keeps_subcommand_for_known_tool():
    assert hi.normalize_cmd("git commit -m 'x'") == "git commit"
    assert hi.normalize_cmd("uv run pytest -q") == "uv run"
    assert hi.normalize_cmd("docker compose up -d") == "docker compose"


def test_normalize_cmd_unknown_tool_groups_by_basename():
    # An arbitrary project tool the script has never seen still groups cleanly.
    assert hi.normalize_cmd("rg --files-with-matches foo") == "rg"


def test_normalize_cmd_skips_leading_env_assignments():
    assert hi.normalize_cmd("PYTHONUTF8=1 FOO=bar python app.py") == "python"


def test_normalize_cmd_flag_subtoken_falls_back_to_basename():
    # When the sub-token is a flag, keep just the tool name.
    assert hi.normalize_cmd("go -h") == "go"


def test_normalize_cmd_empty():
    assert hi.normalize_cmd("   ") == "?"


# --- normalize_cmds: compound-command splitting + builtin filtering ---


def test_normalize_cmds_single():
    assert hi.normalize_cmds("pytest -q") == ["pytest"]


def test_normalize_cmds_splits_chain_and_drops_cd():
    # The core review fix: ``cd x && git commit`` must count git, not cd.
    assert hi.normalize_cmds("cd /repo && git commit -m y") == ["git commit"]


def test_normalize_cmds_counts_every_segment():
    assert hi.normalize_cmds("uv run pytest && ruff check") == ["uv run", "ruff"]
    assert hi.normalize_cmds("git add . && git commit") == ["git add", "git commit"]


def test_normalize_cmds_semicolon_and_or():
    assert hi.normalize_cmds("export X=1; make build || echo fail") == ["make build", "echo"]


def test_normalize_cmds_empty():
    assert hi.normalize_cmds("   ") == []


# --- hotspot_dir: derived directory hotspot (no hardcoded path regex) ---


def test_hotspot_dir_last_two_segments():
    assert hi.hotspot_dir("/home/u/proj/src/api/routes.py") == "src/api"


def test_hotspot_dir_drops_windows_drive():
    assert hi.hotspot_dir("c:/Work/app/main.py") == "Work/app"


def test_hotspot_dir_backslashes():
    assert hi.hotspot_dir(r"c:\Work\app\pkg\mod.py") == "app/pkg"


def test_hotspot_dir_bare_file_has_no_hotspot():
    assert hi.hotspot_dir("README.md") == ""


# --- user_text: harness-injected noise is dropped, real prompts kept ---


def test_user_text_drops_noise_prefix():
    assert hi.user_text("<system-reminder>do x</system-reminder>") == ""
    assert hi.user_text("[Request interrupted by user]") == ""


def test_user_text_keeps_real_prompt():
    assert hi.user_text("기간 7일 인사이트 정리해줘") == "기간 7일 인사이트 정리해줘"


def test_user_text_list_blocks_filtered():
    content = [
        {"type": "text", "text": "<ide_selection>noise</ide_selection>"},
        {"type": "text", "text": "real ask"},
        {"type": "tool_result", "text": "ignored"},
    ]
    assert hi.user_text(content) == "real ask"


# --- extract: end-to-end over a synthetic transcript dir ---


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def test_extract_aggregates_prompts_and_tools(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    recs = [
        {
            "type": "user",
            "sessionId": "s1",
            "timestamp": "2099-01-01T00:00:00.000Z",
            "message": {"content": "do the thing"},
        },
        {
            "type": "assistant",
            "timestamp": "2099-01-01T00:01:00.000Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "git status"}},
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": "/home/u/proj/src/api/x.py"},
                    },
                ]
            },
        },
    ]
    _write_jsonl(proj / "a.jsonl", recs)

    prompts, tools, cmds, edits, dirs, sessions = hi.extract([str(proj)], days=3650 * 100)

    assert [t for _, t in prompts] == ["do the thing"]
    assert tools["Bash"] == 1 and tools["Edit"] == 1
    assert cmds["git status"] == 1
    assert edits["x.py"] == 1
    assert dirs["src/api"] == 1
    assert sessions == {"s1"}


def test_extract_drops_records_outside_window(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    recs = [
        {
            "type": "user",
            "sessionId": "old",
            "timestamp": "2000-01-01T00:00:00.000Z",
            "message": {"content": "ancient prompt"},
        },
    ]
    _write_jsonl(proj / "a.jsonl", recs)
    # mtime pre-filter would exclude this anyway; assert the record-level ts
    # filter also drops it when the file mtime is recent.
    prompts, *_ = hi.extract([str(proj)], days=3650 * 100)
    assert any(t == "ancient prompt" for _, t in prompts)  # within 100y window
    prompts, *_ = hi.extract([str(proj)], days=1)
    assert prompts == []  # outside a 1-day window
