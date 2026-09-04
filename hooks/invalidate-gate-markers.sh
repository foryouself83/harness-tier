#!/usr/bin/env bash
# PostToolUse hook — an edit voids the review and doc-sync evidence.
#
# Those two gates judge the working tree, and their markers are branch-bound: they outlive the
# commit that used them. Left in place, a fix made after either passed commits against a marker
# earned over code no reviewer and no doc pass ever saw. They come in a pair because they
# invalidate each other — a review finding is fixed after doc-sync ran, and the fix is then
# undocumented — so the only stable state is "both recorded, nothing edited since".
#
# Deleting is the safe direction: a marker that should have survived costs a re-run, one that
# should have gone lets an unreviewed commit through. Hence every undecidable case deletes, and
# every failure of this hook leaves the markers alone (FAIL-OPEN — the gate keeps the stricter
# answer it already had).
#
# bump and security are deliberately not here: they record a promotion-time decision taken on a
# clean tree, where no edit follows to invalidate anything.

set -uo pipefail

MARKERS="review.done doc-sync.done"
EVIDENCE=".claude/harness-tier/.flow"

# Which tree's evidence this edit outdated — asked of the edited file, not of the session. The
# gate judges a commit against the repo root it is issued in, worktrees included (Invariant 6),
# so the evidence that went stale is the one at the edited file's OWN root. Walking to that root
# rather than to the first evidence dir is what bounds the walk: a scratchpad file has no root
# above it, and a project two levels up never has its evidence taken away by an edit below it.
root_for() {
  local dir="$1"
  while [ -n "$dir" ]; do
    if [ -e "$dir/.git" ]; then  # a clone's is a directory, a worktree's a file — both are roots
      printf '%s' "$dir"
      return 0
    fi
    case "$dir" in
      */*) dir="${dir%/*}" ;;
      *) return 1 ;;
    esac
  done
  return 1
}

# Where a root keeps its git data — one answer shared by every worktree of the same repo, which
# is how two roots are told apart from two views of one repo. Read, not asked of `git`: this runs
# on every edit, and the file says it.
common_dir() {
  local root="$1" line
  if [ -d "$root/.git" ]; then
    printf '%s' "$root/.git"
    return 0
  fi
  [ -f "$root/.git" ] || return 1
  IFS= read -r line < "$root/.git" || return 1
  case "$line" in gitdir:*) line="${line#gitdir:}" ;; *) return 1 ;; esac
  line="${line# }"
  line="${line%/worktrees/*}"                  # a linked worktree points inside the common dir
  case "$line" in /*|?:/*) ;; *) line="$root/$line" ;; esac  # a relative gitdir is root-relative
  printf '%s' "$line"
}

payload="$(cat 2>/dev/null)" || payload=""
# The FIRST match, not the last: `tool_response` echoes a path of its own after `tool_input`,
# and a greedy read would let the response decide where the edit landed. `NotebookEdit` spells
# the key differently, and unread it is a payload with no path at all.
path="$(printf '%s' "$payload" |
  grep -o '"\(file\|notebook\)_path"[[:space:]]*:[[:space:]]*"[^"]*"' |
  head -n 1 |
  sed 's/.*:[[:space:]]*"//; s/"$//')"
# The one spelling this hook reads paths in, applied to everything it compares: bash takes only
# one of the OS's separators as a path, and the session's project dir arrives in the OS's, not
# the payload's. JSON doubles every backslash, so each separator lands as `//` — which the
# filesystem swallows but no glob matches, and the evidence-dir exemption below is a glob. The
# leading run is set rather than squeezed: one slash is an absolute path, two are a share, and
# the doubling makes a share's pair arrive as four. (Nothing here can tell those two apart —
# neither Linux nor MSYS hands out a share to build the case on — so that line is read, not
# measured.)
to_slash() {
  local s="${1//\\//}" lead
  lead="${s%%[!/]*}"
  case "$lead" in "" | /) ;; *) lead="//" ;; esac
  s="$lead$(printf %s "${s#"${s%%[!/]*}"}" | tr -s /)"
  printf '%s' "${s%/}"
}

path="$(to_slash "$path")"
case "$path" in
  */"$EVIDENCE"/*) exit 0 ;;  # the evidence dir writes its own files
esac

# Every tree whose gate could judge this edit. The edited file's root is the first; the session's
# project dir is the second whenever it is another view of the SAME repo, because the gate cannot
# always name the worktree a commit belongs to — a detached HEAD, a branch matching no worktree
# entry — and falls back to reading the project dir (Invariant 6, which keeps that uncertainty
# pointed at main). Voiding both keeps this hook a superset of whichever answer the gate reaches;
# voiding only one leaves the gate reading a marker no edit ever touched.
targets=""
case "$path" in
  */*)
    edited="$(root_for "${path%/*}")" || edited=""
    project="$(to_slash "${CLAUDE_PROJECT_DIR:-}")"
    if [ -n "$edited" ]; then
      targets="$edited"
      if [ -n "$project" ] && [ "$project" != "$edited" ]; then
        here="$(common_dir "$edited")" || here=""
        there="$(common_dir "$project")" || there=""
        # Union unless the two are provably DIFFERENT repos, and ask that of the filesystem
        # rather than of the strings: a relative `gitdir:`, a `..` left in one, a case-different
        # spelling of one directory, or a project dir that is not a root at all all compare
        # unequal as text while naming the same repo. Both must EXIST for the answer to be a
        # proof — `-ef` is false for a path that names nothing (a worktree whose repo moved,
        # an external git dir since deleted), and that false is no evidence of anything.
        # Unproven counts as the same tree: keeping a marker is the direction that lets an
        # unreviewed commit through.
        if [ -e "$here" ] && [ -e "$there" ] && [ ! "$here" -ef "$there" ]; then
          :
        else
          targets="$targets
$project"
        fi
      fi
    fi
    ;;
  *)
    # No path, or a bare name this hook cannot place: it cannot tell where the edit landed, and
    # keeping a marker over an edit nobody has seen is the one direction it may never fail in.
    targets="$(to_slash "${CLAUDE_PROJECT_DIR:-}")"
    ;;
esac
[ -n "$targets" ] || exit 0

voided=""
while IFS= read -r target; do
  [ -n "$target" ] || continue
  flow="$target/$EVIDENCE"
  [ -d "$flow" ] || continue
  for marker in $MARKERS; do
    [ -e "$flow/$marker" ] || continue
    rm -f "$flow/$marker" 2>/dev/null || continue
    case " $voided " in
      *" ${marker%.done} "*) ;;
      *) voided="${voided}${voided:+, }${marker%.done}" ;;
    esac
  done
done <<EOF
$targets
EOF
[ -n "$voided" ] || exit 0

# Only when something was actually voided: on every edit this is noise, on none the agent
# re-runs a gate it does not know it lost.
printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}
'   "harness-tier: this edit voided the ${voided} gate evidence. Re-run those gates before committing."
