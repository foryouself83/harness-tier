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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
RULE_FILE="${PLUGIN_ROOT}/rules/risk-tiers.md"

# If the rule file is absent there is nothing to inject, so exit quietly (FAIL-OPEN).
[ -f "$RULE_FILE" ] || exit 0
rule_content="$(cat "$RULE_FILE" 2>/dev/null)" || exit 0

# Escape the JSON string via bash parameter substitution (faster than a per-character loop).
escape_for_json() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

# --- out-of-date plugin notice -----------------------------------------------
# plugin.json's `version` is the update-gating SSOT, so a consumer whose installed build is older
# than the one the marketplace publishes is running code the maintainer has already replaced —
# and nothing else tells them. Both numbers are local files: the loaded build's own manifest, and
# the marketplace clone Claude Code keeps beside the install cache. No network, so a stale or
# absent clone simply means no notice. Every uncertain branch stays silent: FAIL-OPEN, because a
# hook that runs before the session does must never delay or break it.

manifest_pair() {  # <file> -> "<name>\t<version>", the FIRST of each, read without a subprocess
  # Fork-free: this runs at session start, and a grep|head|sed pipeline per key costs more than
  # the whole rest of the hook. First match wins, so a nested `author.name` after the top-level
  # one does not shadow it — which is the real manifest's layout.
  local line name="" version=""
  while IFS= read -r line || [ -n "$line" ]; do
    if [ -z "$name" ] && [[ $line =~ \"name\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]]; then
      name="${BASH_REMATCH[1]}"
    fi
    if [ -z "$version" ] && [[ $line =~ \"version\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]]; then
      version="${BASH_REMATCH[1]}"
    fi
    [ -n "$name" ] && [ -n "$version" ] && break
  done < "$1"
  printf '%s\t%s' "$name" "$version"
}

safe_token() {  # <value> -> the value, or nothing when it holds anything but a name/version char
  # A marketplace clone is fetched, not authored here, so its values are untrusted input and are
  # dropped rather than escaped. A raw control byte would make escape_for_json emit JSON the host
  # cannot parse — taking the rule injection down with it — and `<`/`>` would let a value close
  # the notice's own tag and write into the context.
  case "$1" in
    "" | *[!A-Za-z0-9._+-]*) return 0 ;;
    *) printf '%s' "$1" ;;
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
  local a="$1" b="$2" ap="" bp="" i x y
  case "$a" in *-*) ap="${a#*-}"; a="${a%%-*}" ;; esac
  case "$b" in *-*) bp="${b#*-}"; b="${b%%-*}" ;; esac
  case "$a$b" in *[!0-9.]*) return 1 ;; esac
  local -a A B
  IFS=. read -r -a A <<< "$a"
  IFS=. read -r -a B <<< "$b"
  { [ "${#A[@]}" -eq 3 ] && [ "${#B[@]}" -eq 3 ]; } || return 1
  for i in 0 1 2; do
    x="${A[i]}"; y="${B[i]}"
    { [ -n "$x" ] && [ -n "$y" ]; } || return 1
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

plugins_root() {  # the directory holding both `cache/` and `marketplaces/`, or nothing
  # Derived by walking up from the loaded build rather than assuming ~/.claude/plugins, which
  # CLAUDE_CONFIG_DIR can relocate. A plugin loaded from a source tree finds no marketplaces
  # sibling and the feature simply does not apply.
  local at="$PLUGIN_ROOT" _
  for _ in 1 2 3 4 5 6; do
    # Substitution, not `dirname`: six forks is most of what this hook costs, and it runs
    # on the critical path of every session start. Both separators, since the variable is
    # whatever the host set.
    at="${at%[/\\]}"
    case "$at" in *[/\\]*) at="${at%[/\\]*}" ;; *) return 0 ;; esac
    [ -d "$at/marketplaces" ] && printf '%s' "$at" && return 0
  done
}

published_notice() {
  local root loaded pair name version pub_version market
  loaded="${PLUGIN_ROOT}/.claude-plugin/plugin.json"
  # `-f` is also what stops a FIFO on either path from blocking the hook forever — the read below
  # has no timeout and nothing downstream does either.
  [ -f "$loaded" ] || return 0
  pair="$(manifest_pair "$loaded")"
  name="$(safe_token "${pair%%$'\t'*}")"
  version="$(safe_token "${pair##*$'\t'}")"
  { [ -n "$name" ] && [ -n "$version" ]; } || return 0
  root="$(plugins_root)"
  [ -n "$root" ] || return 0
  for market in "$root"/marketplaces/*/.claude-plugin/plugin.json; do
    [ -f "$market" ] || continue
    pair="$(manifest_pair "$market")"
    # A marketplace that publishes several plugins carries no root manifest, and one that
    # publishes a different plugin is not this plugin's publisher.
    [ "${pair%%$'\t'*}" = "$name" ] || continue
    pub_version="$(safe_token "${pair##*$'\t'}")"
    { [ -n "$pub_version" ] && [ "$pub_version" != "$version" ]; } || return 0
    # Announce only when the marketplace is AHEAD. A maintainer running a release candidate
    # is ahead of what is published, and telling them to update would name a remedy that
    # fetches the older pin — noise nothing can clear.
    version_gt "$pub_version" "$version" || return 0
    printf '[%s] 설치된 버전은 %s 인데 마켓플레이스는 %s 를 게시하고 있습니다. /plugin 에서 업데이트하세요.' \
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
notice="$(published_notice)"
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
  notice_block="<harness-tier-stale-build>\nRelay this to the user before doing anything else:\n$(escape_for_json "$notice")\n</harness-tier-stale-build>\n\n"
fi

rule_escaped="$(escape_for_json "$rule_content")"
session_context="${notice_block}<harness-tier-risk-tiers>\nThis project enforces the harness-tier risk-tiered workflow AT COMMIT TIME. The commit gate is fail-closed: it blocks any commit whose task was not classified by /flow. So before starting ANY code change, feature, fix, or dev request — and at the latest before you commit — your action MUST be to invoke the /flow skill (via the Skill tool). /flow is what classifies the task, confirms the tier, runs the matching gates, and records the marker the commit gate requires. Do NOT judge the tier yourself and skip the skill; without /flow's marker the commit is rejected.\n\n${rule_escaped}\n</harness-tier-risk-tiers>"

if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context"
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context"
fi

exit 0
