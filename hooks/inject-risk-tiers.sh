#!/usr/bin/env bash
# SessionStart hook — injects the risk-tiers rule into the session context, and tells a consumer
# when the marketplace publishes a newer build than the one this session loaded.
#
# Since the plugin's rules/ is not auto-loaded (unlike ras_llm's .claude/rules auto-load),
# this hook stands in for an always-on rule and injects risk-tiers.md every session.
# On missing file / read failure, it passes quietly with an empty injection (FAIL-OPEN).
#
# Output convention (superpowers session-start pattern):
#   - Cursor      : additional_context (snake_case, top-level)
#   - Claude Code : hookSpecificOutput.additionalContext (nested)
#   - others (SDK): additionalContext (top-level)
# heredoc has a hang issue on bash 5.3+, so we output via printf.

set -uo pipefail
# Byte-wise throughout: every pattern here is ASCII and every output a byte copy. Under a
# multibyte locale bash's `${s//…}` rescans the string per match, quadratic on a non-ASCII
# rule. Set once: a `local LC_ALL` per call reloads the caller's locale on every return.
LC_ALL=C

# Which harness sent the payload. No argument is Claude Code, which every existing host is.
# Any other argument is a mistyped hook entry. The session still gets the Claude-shaped rule —
# no rule at all is worse than the wrong invocation form — and a block naming the bad entry, so
# it is seen at session start rather than at the first blocked commit.
HARNESS=claude
if [ "$#" -gt 0 ]; then
  case "$#:$1:${2:-}" in
    2:--harness:claude | 2:--harness:codex) HARNESS=$2 ;;
    *)
      HARNESS=unknown
      printf '%s: unknown arguments "%s" (expected --harness claude|codex)\n' "${0##*/}" "$*" >&2
      # Printable ASCII only: escape_for_json passes other control bytes and invalid UTF-8
      # through, and either one makes the whole injection unparseable. No `<` or `>` either, so
      # the arguments cannot close the block they are quoted in.
      ARGS="$(LC_ALL=C; a="$*"; a="${a//[![:print:]]/?}"; printf '%s' "${a//[<>]/?}")"
      ;;
  esac
fi

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
[ -n "$PLUGIN_ROOT" ] || PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RULE_FILE="${PLUGIN_ROOT}/rules/risk-tiers.md"

# Every helper below returns through the variable its caller names, never through `$(...)`:
# each command substitution is a fork. Git Bash 5.2 on the shipped rule, median of 7: 1050 ms
# per session start with ten of them, 126 ms with none, 105 ms for a bare `bash -c :`.

# The helpers' `printf -v` targets, declared where ShellCheck can see them assigned.
rule_escaped="" rules_dir_escaped="" notice_escaped="" args_escaped="" tools_escaped=""

# If the rule file is absent there is nothing to inject, so exit quietly (FAIL-OPEN).
# `$(<file)` is read in the shell itself from bash 5.2 on, where `read -d ''` costs a syscall
# per byte on msys.
[ -f "$RULE_FILE" ] || exit 0
{ rule_content="$(<"$RULE_FILE")"; } 2>/dev/null || exit 0

# The same escaping, one awk process instead of five substitutions, for bash 3 (macOS
# /bin/bash), which copies the whole string per match. Whole hook on the shipped rule, bash
# 3.2.57 self-built in WSL on a native filesystem, median of 15: 290 ms with the substitutions,
# 11 ms with awk. On bash 4.4 the two paths measured within noise of each other, so bash 4 and
# later keep the substitutions, and Git Bash (5.2) spends no fork on them.
# The trailing x keeps a final newline from being read as the end of the last record.
# shellcheck disable=SC2016 # awk's own program text: nothing in it is for the shell to expand.
json_escape_awk='{
  if (NR > 1) printf "%s", "\\n"
  n = length($0); out = ""
  for (i = 1; i <= n; i++) {
    c = substr($0, i, 1)
    if (c == "\\") c = "\\\\"
    else if (c == "\"") c = "\\\""
    else if (c == "\r") c = "\\r"
    else if (c == "\t") c = "\\t"
    out = out c
  }
  printf "%s", out
}'

# Escape the JSON string via bash parameter substitution (faster than a per-character loop).
# Every escape is ASCII and no UTF-8 continuation byte is, so the C locale's byte-wise pass
# writes what a character-wise one would. An awk that fails leaves the bash path.
escape_for_json() {  # <var> <value>
  local _s
  if [ "${BASH_VERSINFO[0]}" -lt 4 ] &&
     _s="$(printf '%sx' "$2" | LC_ALL=C awk "$json_escape_awk")"; then
    printf -v "$1" '%s' "${_s%x}"
    return 0
  fi
  _s="$2"
  _s="${_s//\\/\\\\}"
  _s="${_s//\"/\\\"}"
  _s="${_s//$'\n'/\\n}"
  _s="${_s//$'\r'/\\r}"
  _s="${_s//$'\t'/\\t}"
  printf -v "$1" '%s' "$_s"
}

# --- out-of-date plugin notice -----------------------------------------------
# plugin.json's `version` is the update-gating SSOT, so a consumer whose installed build is older
# than the one the marketplace publishes is running code the maintainer has already replaced —
# and nothing else tells them. Both numbers are local files: the loaded build's own manifest, and
# the marketplace clone Claude Code keeps beside the install cache. No network, so a stale or
# absent clone means no notice. Every uncertain branch stays silent: FAIL-OPEN, because a
# hook that runs before the session does must never delay or break it.

manifest_pair() {  # <file> -> manifest_name, manifest_version: the FIRST of each
  # Fork-free: this runs at session start, and a grep|head|sed pipeline per key costs more than
  # the whole rest of the hook. First match wins, so a nested `author.name` after the top-level
  # one does not shadow it — which is the real manifest's layout.
  local line
  manifest_name="" manifest_version=""
  while IFS= read -r line || [ -n "$line" ]; do
    if [ -z "$manifest_name" ] &&
       [[ $line =~ \"name\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]]; then
      manifest_name="${BASH_REMATCH[1]}"
    fi
    if [ -z "$manifest_version" ] &&
       [[ $line =~ \"version\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]]; then
      manifest_version="${BASH_REMATCH[1]}"
    fi
    [ -n "$manifest_name" ] && [ -n "$manifest_version" ] && break
  done < "$1"
}

safe_token() {  # <var> <value>: the value, or nothing when it holds anything but a name/version char
  # A marketplace clone is fetched, not authored here, so its values are untrusted input and are
  # dropped rather than escaped. A raw control byte would make escape_for_json emit JSON the host
  # cannot parse — taking the rule injection down with it — and `<`/`>` would let a value close
  # the notice's own tag and write into the context.
  case "$2" in
    "" | *[!A-Za-z0-9._+-]*) printf -v "$1" '%s' "" ;;
    *) printf -v "$1" '%s' "$2" ;;
  esac
}

version_gt() {  # <a> <b> -> 0 when a has higher semver precedence than b, 1 otherwise
  # `sort -V` cannot answer this: it ranks 1.0.0-rc.1 ABOVE 1.0.0, and every release this repo
  # ships passes through an rc, so the consumer still on the candidate would never be told the
  # release exists while the consumer on the release would be told to take the candidate back.
  # Semver precedence instead — numeric core first, then a prerelease ranks BELOW its own core,
  # then identifier by identifier. Pure bash: this runs before the session does, and the pipeline
  # it replaces cost two forks. A version that is not X.Y.Z[-pre] is not ordered at all and the
  # caller stays silent, because direction is the entire content of the notice.
  # LC_ALL is local so the identifier comparison below sorts by byte, as semver 11 requires;
  # `>` inside `[[ ]]` collates in the caller's locale, which is not a property of the input.
  local LC_ALL=C a="$1" b="$2" ap="" bp="" i x y
  a="${a%%+*}"; b="${b%%+*}"        # semver 10: build metadata is not part of the order
  case "$a" in *-*) ap="${a#*-}"; a="${a%%-*}" ;; esac
  case "$b" in *-*) bp="${b#*-}"; b="${b%%-*}" ;; esac
  case "$a$b" in *[!0-9.]*) return 1 ;; esac
  local -a A B
  IFS=. read -r -a A <<< "$a"
  IFS=. read -r -a B <<< "$b"
  { [ "${#A[@]}" -eq 3 ] && [ "${#B[@]}" -eq 3 ]; } || return 1
  for i in 0 1 2; do
    x="${A[i]}"; y="${B[i]}"
    # Non-empty, and short enough for the shell to compare as integers — past that `[ -gt ]`
    # writes a complaint to the stderr of a hook that runs before the session does.
    { [ -n "$x" ] && [ -n "$y" ] && [ "${#x}" -le 18 ] && [ "${#y}" -le 18 ]; } || return 1
    [ "$x" -gt "$y" ] && return 0
    [ "$x" -lt "$y" ] && return 1
  done
  # Equal cores. A build with no prerelease is the finished one, and outranks every candidate.
  [ -n "$ap" ] && [ -z "$bp" ] && return 1
  [ -z "$ap" ] && { [ -n "$bp" ] && return 0 || return 1; }
  local -a P Q
  IFS=. read -r -a P <<< "$ap"
  IFS=. read -r -a Q <<< "$bp"
  i=0
  while [ "$i" -lt "${#P[@]}" ] || [ "$i" -lt "${#Q[@]}" ]; do
    x="${P[i]-}"; y="${Q[i]-}"
    [ -z "$x" ] && return 1          # the shorter identifier list ranks lower
    [ -z "$y" ] && return 0
    if [ "$x" != "$y" ]; then
      case "$x$y" in
        *[!0-9]*)                    # at least one is alphanumeric
          case "$x" in *[!0-9]*) ;; *) return 1 ;; esac   # all-numeric ranks below it
          case "$y" in *[!0-9]*) ;; *) return 0 ;; esac
          [[ $x > $y ]] && return 0 || return 1 ;;
        *) [ "$x" -gt "$y" ] && return 0 || return 1 ;;
      esac
    fi
    i=$((i + 1))
  done
  return 1
}

plugins_root() {  # -> plugins_dir: the directory holding both `cache/` and `marketplaces/`, or ""
  # Derived by walking up from the loaded build rather than assuming ~/.claude/plugins, which
  # CLAUDE_CONFIG_DIR can relocate. A plugin loaded from a source tree finds no marketplaces
  # sibling and the feature does not apply.
  local at="$PLUGIN_ROOT" _
  plugins_dir=""
  for _ in 1 2 3 4 5 6; do
    # Substitution, not `dirname`: six forks is most of what this hook costs, and it runs
    # on the critical path of every session start. Both separators, since the variable is
    # whatever the host set.
    at="${at%[/\\]}"
    case "$at" in *[/\\]*) at="${at%[/\\]*}" ;; *) return 0 ;; esac
    [ -d "$at/marketplaces" ] && plugins_dir="$at" && return 0
  done
}

published_notice() {  # -> notice: the stale-build line, or ""
  local loaded name version pub_version market
  notice=""
  loaded="${PLUGIN_ROOT}/.claude-plugin/plugin.json"
  # `-f` is also what stops a FIFO on either path from blocking the hook forever — the read below
  # has no timeout and nothing downstream does either.
  [ -f "$loaded" ] || return 0
  manifest_pair "$loaded"
  safe_token name "$manifest_name"
  safe_token version "$manifest_version"
  { [ -n "$name" ] && [ -n "$version" ]; } || return 0
  plugins_root
  [ -n "$plugins_dir" ] || return 0
  for market in "$plugins_dir"/marketplaces/*/.claude-plugin/plugin.json; do
    [ -f "$market" ] || continue
    manifest_pair "$market"
    # A marketplace that publishes several plugins carries no root manifest, and one that
    # publishes a different plugin is not this plugin's publisher.
    [ "$manifest_name" = "$name" ] || continue
    safe_token pub_version "$manifest_version"
    [ -n "$pub_version" ] || continue
    # Announce only when the marketplace is AHEAD. A maintainer running a release candidate
    # is ahead of what is published, and telling them to update would name a remedy that
    # fetches the older pin — noise nothing can clear. A clone that is not ahead is not the
    # answer for every clone: `continue`, or whichever directory sorts first decides, and one
    # stale clone hides the update the next one publishes.
    version_gt "$pub_version" "$version" || continue
    printf -v notice '[%s] 설치된 버전은 %s 인데 마켓플레이스는 %s 를 게시하고 있습니다. /plugin 에서 업데이트하세요.' \
      "$name" "$version" "$pub_version"
    return 0
  done
}

# Announce on a fresh session only — repeating it on every clear/compact is noise. The
# source is read only when there IS a notice to suppress: the read carries a timeout, so on
# a session with nothing to say it would be pure latency on the critical path, and the two
# manifest reads that decide it are cheaper than the timeout they would wait out.
# An unreadable source announces rather than going quiet: a notice nobody needed beats a
# feature that silently stopped working.
notice=""
[ "$HARNESS" != codex ] && published_notice
if [ -n "$notice" ]; then
  hook_stdin=""
  IFS= read -r -t 1 -d '' hook_stdin 2>/dev/null || true
  if [[ $hook_stdin =~ \"source\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] &&
     [ "${BASH_REMATCH[1]}" != "startup" ]; then
    notice=""
  fi
fi

# A hook's `systemMessage` reaches no channel this could be observed on, so the notice
# travels in the injected context under its own tag, with the instruction to pass it on.
notice_block=""
if [ -n "$notice" ]; then
  escape_for_json notice_escaped "$notice"
  notice_block="<harness-tier-stale-build>\nRelay this to the user before doing anything else:\n${notice_escaped}\n</harness-tier-stale-build>\n\n"
fi

# The rule links its siblings by bare filename ("[merge-strategy.md](merge-strategy.md)"),
# which reaches a session with no directory to resolve against — the plugin lives in a
# versioned cache. The base path is named AFTER the rule, never before it: text beside the
# mandate moves the skills measured invocation rates, and a path is not worth that.
escape_for_json rule_escaped "$rule_content"
escape_for_json rules_dir_escaped "${PLUGIN_ROOT}/rules"
# The rule's own Principle carries the mandate; Codex gets one line mapping its slash forms.
harness_line=""
if [ "$HARNESS" = codex ]; then
  # shellcheck disable=SC2016 # $flow names Codex's skill form and must stay literal, not expand.
  harness_line='On Codex a slash command below that names a harness-tier skill is that skill, invoked as $name: start with $flow, open its SKILL.md and follow it in full.'"\n\n"
fi
session_context="${notice_block}<harness-tier-risk-tiers>\n${harness_line}${rule_escaped}\n\nThe files this rule links by bare filename live in ${rules_dir_escaped} — read one there when it sends you to it.\n</harness-tier-risk-tiers>"

# A separate block, after the risk-tiers one: the mandate's neighbourhood is measured, and
# text added beside it moves the skills' invocation rates. Names no skill — a slash name
# here would force `hook_assisted` onto it (tests/evals/test_injected_rule.py).
# Skipped where an older /flow-init left the full rule in the host's .claude/rules/ (RULES_DEST
# in flow_init_setup.py), which Claude Code loads itself until a re-sync deletes it. Codex reads
# no .claude/rules/.
prose_block=""
host_rule="${CLAUDE_PROJECT_DIR:-.}/.claude/rules/harness-tier/doc-style.md"
if [ "$HARNESS" = codex ] || [ ! -f "$host_rule" ]; then
  prose_block="\n\n<harness-tier-prose>\nApply this while writing comments, docstrings and docs; restate it in the user's language when you surface it.\n\nWrite the fact in force: no history, commit sha, plan pointer, filler, revision field, or line number after a filename. A number only as a contract or a measurement with its conditions. Prefer code that raises (an assert, a bound, a type) over a comment, and never explain how. A trap with no runtime moment gets the box, its keys untranslated:\n  CRITICAL TRAP: / Trigger: / Symptom:\n\nFull rule: ${rules_dir_escaped}/doc-style.md\n</harness-tier-prose>"
fi
session_context="${session_context}${prose_block}"

# Last, for the same reason the prose block sits apart: nothing new beside the mandate.
if [ "$HARNESS" = unknown ]; then
  escape_for_json args_escaped "$ARGS"
  session_context="${session_context}\n\n<harness-tier-hook-error>\nRelay this to the user before doing anything else: the harness-tier SessionStart hook entry passed unknown arguments \\\"${args_escaped}\\\" (expected --harness claude|codex), so the rule above is in its Claude Code form. Fix the hook entry.\n</harness-tier-hook-error>"
fi

if [ "$HARNESS" = codex ]; then
  tools_file="${PLUGIN_ROOT}/rules/harness-tools/codex.md"
  if [ -f "$tools_file" ] && { tools_content="$(<"$tools_file")"; } 2>/dev/null; then
    escape_for_json tools_escaped "$tools_content"
    session_context="${session_context}\n\n<harness-tier-codex-tools>\n${tools_escaped}\n</harness-tier-codex-tools>"
  fi
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context"
  exit 0
fi

if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context"
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context"
fi

exit 0
