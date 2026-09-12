# Step 2.7 — Merge ruleset check

Loaded by [`/flow-init`](../SKILL.md) Step 2.7. Everything the step does is here; the
skill keeps only the condition that decides whether to read it.

Applies only when `flow-config.merge_workflow.pull_request` is non-empty. Under PR mode the
local `git merge` disappears, so `flow-tiers.yaml`'s `merge_strategy` gate never fires — a
GitHub Ruleset has to carry that enforcement instead. **The block below detects the
not-applicable case itself**: on the shipped `[]` default (or a config that predates the
slot) it prints a skip line and exits 0, so running it is always safe and never reads as a
config defect.

Derive the repo, the branch names, and the selected flow(s) from the config you wrote
in this same command — never type a branch name or flow list by hand. A typed branch name
that doesn't match the config queries a ref that doesn't exist and silently reports a false
mismatch; typing more flows than were selected reports a real gap against a branch the user
never opted into securing. `flows()` below validates its own output before printing
anything — an empty/absent `merge_workflow.pull_request` is the "skip" exit 3, while a
non-list or any value outside `daily`/`promotion` is exit 1 with a stated reason, instead of
silently handing the ruleset check zero (or garbled) arguments. Either way the block stops
here rather than letting the check proceed and report a false "match". Run as written
(`${ROOT}` and `${PLUGIN}` come from [`SKILL.md`](../SKILL.md) Path conventions):

```bash
CFG="${ROOT}/.claude/harness-tier/config/flow-config.yaml"
br() {
  python3 - "$CFG" "$1" <<'PY'
import sys, yaml
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except Exception as e:
    print(f"cannot read {sys.argv[1]}: {e}", file=sys.stderr)
    sys.exit(1)
key = sys.argv[2]
val = (cfg.get("branches") or {}).get(key)
if not isinstance(val, str) or not val:
    print(f"branches.{key} must be a non-empty string, got: {val!r}", file=sys.stderr)
    sys.exit(1)
print(val)
PY
}
flows() {
  python3 - "$CFG" <<'PY'
import sys, yaml
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except Exception as e:
    print(f"cannot read {sys.argv[1]}: {e}", file=sys.stderr)
    sys.exit(1)
pr = (cfg.get("merge_workflow") or {}).get("pull_request")
valid = {"daily", "promotion"}
if pr is None or (isinstance(pr, list) and not pr):
    sys.exit(3)          # PR mode off (the shipped default) — not applicable, not an error
if not isinstance(pr, list) or not set(pr) <= valid:
    print(f"merge_workflow.pull_request must be a list of daily/promotion, "
          f"got: {pr!r}", file=sys.stderr)
    sys.exit(1)
print(" ".join(pr))
PY
}
FLOWS="$(flows)"; frc=$?
if [ "$frc" = 3 ]; then
  echo "  [=] merge_workflow.pull_request is empty — PR mode off, not applicable; skipping"
  exit 0
fi
[ "$frc" = 0 ] || exit 1
BR_INTEGRATION="$(br integration)" || exit 1
BR_STAGING="$(br staging)" || exit 1
BR_PRODUCTION="$(br production)" || exit 1
if ! command -v gh >/dev/null 2>&1; then
  echo "  [=] gh not installed — skipping the ruleset check (install gh to enable it)"
  exit 0
fi
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" || REPO=""
if [ -z "$REPO" ]; then
  echo "  [=] no GitHub repo resolved (no remote, or gh not authenticated) — skipping"
  exit 0
fi
HARNESS_REPO="$REPO" \
HARNESS_BRANCH_INTEGRATION="$BR_INTEGRATION" \
HARNESS_BRANCH_STAGING="$BR_STAGING" \
HARNESS_BRANCH_PRODUCTION="$BR_PRODUCTION" \
  bash "${PLUGIN}/scripts/check-merge-ruleset.sh" $FLOWS
```

(`$FLOWS` is deliberately unquoted — it word-splits the space-joined flow list into
positional arguments, the same idiom `check-merge-ruleset.sh` itself uses for its own
`for id in $ids` loop. `check-merge-ruleset.sh` independently refuses to report "match"
for a zero-arg or all-unrecognized-arg call — belt and braces, since `flows()`/`br()`
above are what should catch a bad config before the script ever runs. Each `br` call — and
the `gh repo view` — is captured into its own variable and checked **before** the invocation
line, not left inline inside it, because only a real assignment statement gives `||`
something to fire on; a broken `branches` subtree (missing key, typo'd name, deleted
value) must stop the block here, never reach the script as a silently empty env var that
`${VAR:-dev}` would absorb into a check against the wrong branch. `REPO` is captured the
same way and non-empty-tested for a related reason: inline, an empty `HARNESS_REPO` falls
through to `${GITHUB_REPOSITORY:-}`, and if *that* happens to be set the script would
cheerfully report "merge rulesets match" for a repo this block never derived. But `REPO`
**skips rather than stops** — a broken `branches` subtree is a config error the user must
fix, whereas an absent or unauthenticated `gh`, or a repo with no GitHub remote, only means
this check is not applicable. The script itself already degrades that case to exit 20, so a
caller that hard-errors on it is stricter than the thing it calls, and would stop
`/flow-init` over a missing CLI.)

The script is **read-only** — it never changes repo settings. It reports the gap between the
current state and what is required, plus how to apply it (the same posture as
`check_precommit`, which reports missing hooks instead of merging them). Relay its output
**verbatim** and continue `/flow-init` on exit 10 (mismatch) and 20 (undetermined — no
`python3`, or a ruleset whose body could not be read) alike.
On a re-run this step doubles as a drift check.
