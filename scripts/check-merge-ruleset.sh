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
#   check-merge-ruleset.sh --decode <branch> <methods-csv> [<default-branch>]
#   check-merge-ruleset.sh --decode-bypass <branch> [<default-branch>]
#     (both read stdin = JSON array of rulesets. <default-branch> resolves the
#      ~DEFAULT_BRANCH alias in conditions.ref_name; omitted, such a ruleset is not counted.)
#
# Env: HARNESS_REPO (else GITHUB_REPOSITORY)
#      HARNESS_BRANCH_INTEGRATION / _STAGING / _PRODUCTION (else dev / stage / main)
# Exit: 0 matches | 10 differs (guidance printed) | 20 undetermined (no tool/repo/parse,
#       or no recognized flow arg — the script must never claim "match" for a check it
#       never ran).
#
# Two INDEPENDENT axes are compared, because a repo can satisfy either one and still be
# broken: the allowed merge methods, and the presence of a bypass actor. Both hang off the
# same "Require a pull request before merging" rule, but only the first is a comparison
# against flow-config; the second is what keeps the release pipeline's direct pushes
# working. Deriving one from the other reports "match" for the configuration that breaks
# releases, so each is decoded on its own.
set -u
# CLAUDE.md Invariant #2 — the host/hook locale is cp949 (or cp1252), so a child python's
# default I/O encoding is NOT UTF-8. Same guard, same place, as check-deps.sh:10 and
# precommit-runner.sh:31.
export PYTHONUTF8=1

# Everything every decoder needs, defined ONCE and prepended to each of them. The ref
# matcher used to be inlined per decoder and drifted incomplete in both copies at the same
# time; a third axis would have repeated the same gap again. Single-quoted, so nothing here
# is shell-expanded, and it must stay free of single quotes.
SHARED_PY='import re
def _rx(p):
    # GitHub ref patterns are PATH-AWARE: * matches within one segment, ** spans them.
    # fnmatch has no such rule (its * swallows /), so refs/heads/* would count a ruleset
    # GitHub never applies to team/dev — a clean verdict for a branch nothing protects.
    # A bracket class is left literal: failing to match only costs a spurious "differs".
    # CEILING: many ** in one pattern backtrack badly (12 of them take ~2s on a 40-char
    # ref, and it grows exponentially). Left as-is because a ref pattern is authored by a
    # repo/org admin, not by untrusted input. To lift it, split the pattern on ** and walk
    # the segments greedily instead of handing one .*-laden regex to re.
    out, i = [], 0
    while i < len(p):
        if p[i:i + 2] == "**":
            out.append(".*")
            i += 2
            continue
        c = p[i]
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return "".join(out)
def unreadable(sets):
    # The fetch loop marks a ruleset whose body it could not read. We do not know whether it
    # governs this ref, so no verdict is honest — the caller exits 20 rather than judging a
    # partial picture.
    return any(rs.get("__unreadable__") for rs in sets)
def _hit(pats, ref, default_branch):
    for p in pats or []:
        if not isinstance(p, str):
            continue
        if p == "~ALL":
            return True
        if p == "~DEFAULT_BRANCH":
            # Only decidable when the caller resolved the repo default. Unknown means NOT
            # matched: over-counting yields a false "match" (unsafe), under-counting only
            # a spurious "differs" (noise).
            if default_branch and ref == "refs/heads/" + default_branch:
                return True
            continue
        if p == ref or re.fullmatch(_rx(p), ref):
            return True
    return False
def applies(rs, ref, default_branch):
    if rs.get("enforcement") != "active":
        return False
    rn = (rs.get("conditions") or {}).get("ref_name") or {}
    # exclude is applied LAST by GitHub and wins over include. Ignoring it counted rulesets
    # that govern nothing here, which is how a repo got a clean verdict for a branch no
    # ruleset actually protected.
    if _hit(rn.get("exclude"), ref, default_branch):
        return False
    return _hit(rn.get("include"), ref, default_branch)
'

decode() {  # $1=branch $2=methods-csv $3=default-branch(may be empty); stdin=JSON array → 0 match / 10 differs / 20 unparsable
  command -v python3 >/dev/null 2>&1 || return 20
  # stdin is read as BYTES and decoded utf-8 explicitly. A ruleset `name` carries arbitrary
  # user text (Korean is the obvious case here) and the GitHub API always answers UTF-8, but
  # the locale — or PYTHONIOENCODING, which outranks even UTF-8 mode — would otherwise pick
  # the codec: one UnicodeDecodeError and a correctly configured repo gets reported as
  # misconfigured. Decoding explicitly makes that impossible regardless of the environment.
  python3 -c "$SHARED_PY"'import json,sys
branch, want = sys.argv[1], set(sys.argv[2].split(","))
default_branch = sys.argv[3] if len(sys.argv) > 3 else ""
try:
    sets = json.loads(sys.stdin.buffer.read().decode("utf-8"))
except Exception:
    sys.exit(20)
if not isinstance(sets, list) or not all(isinstance(rs, dict) for rs in sets):
    sys.exit(20)
if unreadable(sets):
    sys.exit(20)
ref = "refs/heads/" + branch
got = None
for rs in sets:
    if not applies(rs, ref, default_branch):
        continue
    for rule in rs.get("rules") or []:
        if rule.get("type") != "pull_request":
            continue
        methods = (rule.get("parameters") or {}).get("allowed_merge_methods")
        if methods is None:
            continue
        # GitHub applies the INTERSECTION when several rulesets match the same ref.
        got = set(methods) if got is None else (got & set(methods))
sys.exit(0 if got == want else 10)' "$1" "$2" "${3:-}"
}

decode_bypass() {  # $1=branch $2=default-branch(may be empty); stdin=JSON array → 0 no gap / 10 a matching ruleset has no actor that can push / 20 unparsable
  command -v python3 >/dev/null 2>&1 || return 20
  # Same explicit utf-8 byte decode and same shape validation as decode() above, for the
  # same reason (a ruleset `name` is free user text; the locale codec must never decide the
  # verdict). Only the question asked of the parsed data differs.
  python3 -c "$SHARED_PY"'import json,sys
branch = sys.argv[1]
default_branch = sys.argv[2] if len(sys.argv) > 2 else ""
try:
    sets = json.loads(sys.stdin.buffer.read().decode("utf-8"))
except Exception:
    sys.exit(20)
if not isinstance(sets, list) or not all(isinstance(rs, dict) for rs in sets):
    sys.exit(20)
if unreadable(sets):
    sys.exit(20)
ref = "refs/heads/" + branch
for rs in sets:
    if not applies(rs, ref, default_branch):
        continue
    # Only a pull_request rule blocks the direct pushes a bypass actor exists to allow. A
    # ruleset without one imposes nothing to bypass — reporting 0 there is a determination,
    # not a skipped check.
    if not any(isinstance(r, dict) and r.get("type") == "pull_request" for r in rs.get("rules") or []):
        continue
    # Bypass is PER-RULESET, not intersected like the merge methods: an actor listed on
    # ruleset A does not exempt the push from ruleset B. One gap is enough to block it.
    #
    # Presence alone is not enough either. `bypass_mode` decides WHAT the actor may bypass:
    # "pull_request" lets them merge a non-compliant PR but NOT push directly — and a direct
    # push is exactly what the release pipeline needs. Counting such an actor would repeat,
    # one level down, the bug this whole check exists for. Every other value — including one
    # this script has not seen, or an omitted key — is read as permissive, so a field we
    # cannot interpret never fails a correctly configured repo.
    if not any(
        isinstance(a, dict) and a.get("bypass_mode", "always") != "pull_request"
        for a in rs.get("bypass_actors") or []
    ):
        sys.exit(10)
sys.exit(0)' "$1" "${2:-}"
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
  # Said once, in the shared helper, because it applies to both callers — and because a
  # reader can reach this warning with an actor already listed. Without it that reader sees
  # an actor, assumes the check is wrong, and changes nothing.
  echo "      It must be able to push DIRECTLY: bypass_mode 'always', not 'pull_request'" >&2
  echo "      (a 'pull_request' actor may merge a non-compliant PR but not push)." >&2
  shift 2
  for line in "$@"; do
    echo "      $line" >&2
  done
}

if [ "${1:-}" = "--decode" ]; then
  decode "${2:-}" "${3:-}" "${4:-}"
  exit $?
fi

if [ "${1:-}" = "--decode-bypass" ]; then
  decode_bypass "${2:-}" "${3:-}"
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

# Resolved once, for the ~DEFAULT_BRANCH alias in conditions.ref_name. An empty value is a
# valid answer, not an error: the matcher then declines to count such a ruleset, which errs
# toward "differs" rather than a false "match".
default_branch="$(gh api "repos/$repo" --jq '.default_branch' 2>/dev/null)" || default_branch=""

# Full ruleset objects: the list endpoint omits `rules`, so each id is fetched individually.
# NOTE: no leading slash on the api path — `gh api` on Git Bash/MSYS mangles a leading
# "/repos/..." into a filesystem path (e.g. "C:/Program Files/Git/repos/...") before it
# ever reaches gh; the leading slash is not required by the API and must stay off.
sets="$(
  ids="$(gh api "repos/$repo/rulesets" --jq '.[].id' 2>/dev/null)" || exit 1
  owner="${repo%%/*}"
  printf '['
  first=1
  for id in $ids; do
    [ "$first" = 1 ] || printf ','
    first=0
    # The list includes rulesets INHERITED from the org, whose bodies are not readable at the
    # repo-scoped id endpoint — they live under orgs/. Letting one such id abort the loop
    # made the whole check a permanent exit 20 for every org that manages rulesets centrally:
    # it switched itself off for exactly the repos it was meant to inspect. A failure now
    # stays scoped to its own id, and only when neither endpoint answers does the body become
    # a marker the decoders read as "undetermined" — never a verdict on an unread ruleset.
    gh api "repos/$repo/rulesets/$id" 2>/dev/null \
      || gh api "orgs/$owner/rulesets/$id" 2>/dev/null \
      || printf '{"__unreadable__": true}'
  done
  printf ']'
)" || { echo "  [=] could not read rulesets — skipping" >&2; exit 20; }

check() {  # $1=branch $2=methods-csv → 0 match | 1 differs (guidance printed) | 2 undetermined
  printf '%s' "$sets" | decode "$1" "$2" "$default_branch"
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

check_bypass() {  # $1=branch → 0 ok | 1 gap | 2 undetermined
  printf '%s' "$sets" | decode_bypass "$1" "$default_branch"
  bdrc=$?   # not `brc` — the daily arm holds this function's RESULT in that name
  case "$bdrc" in
    0) return 0 ;;
    # Undecodable is not a gap, for the same reason it is not a mismatch (see check). No
    # message here: check() has already narrated it for this very branch.
    20) return 2 ;;
    *) return 1 ;;
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
      check "$integration" "rebase,squash"; mrc=$?
      check_bypass "$integration"; brc=$?
      case "$mrc" in 2) undetermined=1 ;; esac
      case "$brc" in 2) undetermined=1 ;; esac
      # Either gap earns the same guidance. A method mismatch needs it because the fix —
      # creating or correcting the ruleset — is what introduces the PR requirement in the
      # first place; a bypass gap needs it because the requirement is already there and
      # already rejecting the push.
      if [ "$mrc" = 1 ] || [ "$brc" = 1 ]; then
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
      fi
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
        check_bypass "$b"
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
