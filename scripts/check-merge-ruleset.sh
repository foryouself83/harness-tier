#!/usr/bin/env bash
# Report whether the repo's GitHub rulesets match what flow-config.merge_workflow requires.
#
# READ-ONLY. It never creates or changes a ruleset — it reads, compares, and prints what to
# apply. Same posture as flow_init_setup.check_precommit (reports missing hooks instead of
# merging) and the workflow renderers (never overwrite). Applying a PR-required ruleset to a
# promotion branch is high blast radius — a missing bypass actor stops the release pipeline —
# so that decision stays with the repo owner.
#
# Usage:
#   check-merge-ruleset.sh <flow> [<flow>...]        # flow = daily | promotion
#   check-merge-ruleset.sh --decode <branch> <methods-csv>   # stdin = JSON array of rulesets
#
# Env: HARNESS_REPO (else GITHUB_REPOSITORY)
#      HARNESS_BRANCH_INTEGRATION / _STAGING / _PRODUCTION (else dev / stage / main)
# Exit: 0 matches | 10 differs (guidance printed) | 20 undetermined (no tool/repo/parse,
#       or no recognized flow arg — the script must never claim "match" for a check it
#       never ran).
set -u
# CLAUDE.md Invariant #2 — the host/hook locale is cp949 (or cp1252), so a child python's
# default I/O encoding is NOT UTF-8. Same guard, same place, as check-deps.sh:10 and
# precommit-runner.sh:31.
export PYTHONUTF8=1

decode() {  # $1=branch $2=methods-csv; stdin=JSON array → 0 match / 10 differs / 20 unparsable
  command -v python3 >/dev/null 2>&1 || return 20
  # stdin is read as BYTES and decoded utf-8 explicitly. A ruleset `name` carries arbitrary
  # user text (Korean is the obvious case here) and the GitHub API always answers UTF-8, but
  # the locale — or PYTHONIOENCODING, which outranks even UTF-8 mode — would otherwise pick
  # the codec: one UnicodeDecodeError and a correctly configured repo gets reported as
  # misconfigured. Decoding explicitly makes that impossible regardless of the environment.
  python3 -c 'import json,sys
branch, want = sys.argv[1], set(sys.argv[2].split(","))
try:
    sets = json.loads(sys.stdin.buffer.read().decode("utf-8"))
except Exception:
    sys.exit(20)
if not isinstance(sets, list) or not all(isinstance(rs, dict) for rs in sets):
    sys.exit(20)
ref = "refs/heads/" + branch
got = None
for rs in sets:
    if rs.get("enforcement") != "active":
        continue
    inc = ((rs.get("conditions") or {}).get("ref_name") or {}).get("include") or []
    if ref not in inc and "~ALL" not in inc:
        continue
    for rule in rs.get("rules") or []:
        if rule.get("type") != "pull_request":
            continue
        methods = (rule.get("parameters") or {}).get("allowed_merge_methods")
        if methods is None:
            continue
        # GitHub applies the INTERSECTION when several rulesets match the same ref.
        got = set(methods) if got is None else (got & set(methods))
sys.exit(0 if got == want else 10)' "$1" "$2"
}

guide() {  # $1=branch $2=methods-csv — printed on a mismatch; no command is executed
  echo "  [!] $1: allowed merge methods must be exactly: $2" >&2
  echo "      Settings -> Rules -> Rulesets -> New branch ruleset" >&2
  echo "      target ref: refs/heads/$1 | enforcement: active" >&2
  echo "      rule: Require a pull request before merging" >&2
  echo "            Allowed merge methods = $2" >&2
  echo "      docs: https://docs.github.com/en/rest/repos/rules" >&2
}

warn_bypass() {  # $1=scope label $2=what the bypass unblocks $3.. = detail lines
  echo "  [!] $1: add a BYPASS ACTOR for $2." >&2
  shift 2
  for line in "$@"; do
    echo "      $line" >&2
  done
}

if [ "${1:-}" = "--decode" ]; then
  decode "${2:-}" "${3:-}"
  exit $?
fi

integration="${HARNESS_BRANCH_INTEGRATION:-dev}"
staging="${HARNESS_BRANCH_STAGING:-stage}"
production="${HARNESS_BRANCH_PRODUCTION:-main}"
repo="${HARNESS_REPO:-${GITHUB_REPOSITORY:-}}"

if [ -z "$repo" ] || ! command -v gh >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "  [=] gh/python3/repo unavailable — skipping ruleset check" >&2
  exit 20
fi

# Full ruleset objects: the list endpoint omits `rules`, so each id is fetched individually.
# NOTE: no leading slash on the api path — `gh api` on Git Bash/MSYS mangles a leading
# "/repos/..." into a filesystem path (e.g. "C:/Program Files/Git/repos/...") before it
# ever reaches gh; the leading slash is not required by the API and must stay off.
sets="$(
  ids="$(gh api "repos/$repo/rulesets" --jq '.[].id' 2>/dev/null)" || exit 1
  printf '['
  first=1
  for id in $ids; do
    [ "$first" = 1 ] || printf ','
    first=0
    gh api "repos/$repo/rulesets/$id" 2>/dev/null || exit 1
  done
  printf ']'
)" || { echo "  [=] could not read rulesets — skipping" >&2; exit 20; }

check() {  # $1=branch $2=methods-csv → 0 match | 1 differs (guidance printed) | 2 undetermined
  printf '%s' "$sets" | decode "$1" "$2"
  drc=$?
  case "$drc" in
    0) return 0 ;;
    # A response we could not decode is NOT a mismatch. Collapsing it into 10 would report
    # "your ruleset differs" for a repo whose ruleset was never actually read — the exact
    # wrong verdict the 0/10/20 contract at the top of this file exists to prevent.
    20) echo "  [=] $1: ruleset response could not be decoded - undetermined" >&2; return 2 ;;
    *) guide "$1" "$2"; return 1 ;;
  esac
}

rc=0
undetermined=0
checked=0
for flow in "$@"; do
  case "$flow" in
    daily)
      checked=1
      # feature/* is Squash and fix/* is Rebase, so integration allows both and bars a
      # merge commit. Narrowing to squash alone would block the fix/* path. Note this is
      # weaker than the local gate: a branch ruleset targets the DESTINATION ref, so it
      # cannot tell feature/* from fix/* — "no merge commit" is all it can guarantee.
      check "$integration" "rebase,squash"
      case "$?" in
        1)
          rc=10
          # "Require a pull request" comes bundled with allowed_merge_methods, and it also
          # rejects the post-release back-merge push — which risk-tiers.md calls not optional.
          warn_bypass "$integration" "the post-release back-merge" \
            "Allowed merge methods hang off 'Require a pull request before merging', which" \
            "also rejects 'git push origin $integration' — how the production -> integration" \
            "back-merge lands. Without it the released tag is unreachable from $integration" \
            "and semantic-release miscomputes the next version. Routing the back-merge" \
            "through a PR instead does not help: rebase and squash both rewrite SHAs, so the" \
            "tag still never becomes an ancestor. The actor is whoever back-merges: the" \
            "maintainer, or your own automation if you automate that step."
          ;;
        2) undetermined=1 ;;
      esac
      ;;
    promotion)
      checked=1
      promo_rc=0
      for b in "$staging" "$production"; do
        check "$b" "merge"
        case "$?" in
          1) promo_rc=10 ;;
          2) undetermined=1 ;;
        esac
      done
      if [ "$promo_rc" = 10 ]; then
        warn_bypass "promotion branches" "the release automation" \
          "Without it, semantic-release's direct chore(release) push is blocked" \
          "and every release stops. The actor is whoever pushes: the RELEASE_TOKEN" \
          "owner/app if that secret is set, else the github-actions app." \
          "Under this mode hotfix/* -> $production goes through a PR too (the ruleset" \
          "governs every merge into $production) — see risk-tiers.md PR workflow."
        rc=10
      fi
      ;;
    *) echo "  [!] unknown flow: $flow" >&2 ;;
  esac
done
# Zero args, or only unrecognized ones, means no ruleset was actually checked — that must
# never read as "match". Report it as undetermined (20), the same code used for every other
# "couldn't actually run the check" case above.
if [ "$checked" = 0 ]; then
  echo "  [=] no recognized flow given (daily|promotion) — nothing checked" >&2
  exit 20
fi
# Same rule one level up: if any branch came back undecodable, the run as a whole is
# undetermined — never "match", and never "differs" either.
if [ "$undetermined" = 1 ]; then
  echo "  [=] at least one ruleset could not be read — result undetermined" >&2
  exit 20
fi
[ "$rc" = 0 ] && echo "  [=] merge rulesets match the required methods" >&2
exit "$rc"
