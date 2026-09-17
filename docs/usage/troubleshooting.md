# Troubleshooting

**English** · [한국어](troubleshooting.ko.md) · [Usage guide](../../USAGE.md)

The gate's messages are printed in Korean; each heading below quotes the start of one. Every
block described here is layer 2 — a Claude-session commit or merge
([what the gate sees](tiers-and-gates.md#what-the-gate-sees)).

## Blocked — "python3 / PyYAML required"

Message: `게이트에 python3 가 필요합니다` · `게이트에 python 3.8+ 가 필요합니다` ·
`게이트에 PyYAML 이 필요합니다`.

The gate needs `python3` 3.8 or later and PyYAML, whatever your project's language. Without them
it blocks every commit rather than let checks drop out in silence.

```bash
python3 -m pip install pyyaml                       # into the python3 the hook calls
bash .claude/harness-tier/scripts/check-deps.sh    # lists what is missing
```

`uv add` installs into a venv the hook may not see; use `python3 -m pip`.

## Blocked as an unclassified commit

Message: `flow 미진입: 분류되지 않은 커밋입니다.`

No `tier` marker exists for the current branch, so the commit never went through `/flow`. Run
`/flow <task>`; it classifies the work and writes the marker. `/commit` on its own does not
classify. A repo that does not want enforcement removes the gate with
[`/flow-uninstall`](update-and-removal.md#flow-uninstall--remove-host-side-wiring).

## Blocked — evidence missing

Message: `flow 게이트: '<tier>' 티어는 [...] 증거가 필요합니다.` or, on a promotion branch,
`<tier> 게이트 (브랜치 '<branch>'): [...] 증거가 필요합니다.`

The listed gates have no `.done` marker. Either they never ran, or an edit voided them — the
session is told `this edit voided the review, doc-sync gate evidence` when that happens. Re-run
the listed gates through `/flow` (Docs, Dev) or `/release-commit` (Staging, Release). Details in
[gate evidence](tiers-and-gates.md#gate-evidence).

## Blocked — merge strategy

Message: `머지 전략 위반 — '<source>' → '<target>' 는 <flag> 가 필요합니다.` or
`… 에는 <flag> 를 쓰지 않습니다.`

The `git merge` flags break its branch flow's rule. Use the flag the message names; the table is
in [merge strategy](tiers-and-gates.md#merge-strategy). A `[경고] 머지 전략: … rebase 선행이
요구됩니다` line is a warning only — rebase the feature branch first, or ignore it when your
`origin` ref is stale.

## Blocked — module pre-check failed

Message: `모듈 사전검사 실패: <command>.`

A `modules[].checks` command exited nonzero. Its output is printed above the message. Fix the
cause and commit again. Two notes can ride along: files no module covers
(`모듈 미커버라 사전검사 생략`) — add a module if they are new — and an unknown `when` value, read
as `every-commit` ([`modules` and `checks`](configuration.md#modules-and-checks)).

## Blocked — wiki gate

The wiki graph and the documents disagree, or a node changed only its `sources` stamp. Rebuild
with `python3 .claude/harness-tier/scripts/wiki_graph.py --build`, stage `docs/graph/graph.yaml`
with the documents, and commit again. What counts as a violation is in
[`wiki`](tiers-and-gates.md#wiki).

## It blocked me for merely mentioning `git commit`

It should not. The gate reads the command the way a shell does and asks one question: is there
a real `git … commit` in it? A mention inside quotes, a comment or a heredoc body is text, so
`grep "git commit"` and `git log --oneline && echo "now commit"` both run untouched.

One shape trips it on purpose: a command that quotes something commit-shaped and runs a program
the gate does not know to be a reader. Searching and listing tools are known — `grep`, `rg`,
`ls`, `cat`, `head` and their kin run untouched. `awk`, `sed`, `find`, `ack` and `ag` are not,
since each can run a command written in its own arguments, and neither is `git` itself, so
`git log --grep="git commit"` trips it as well. `less` is not among the kin: `LESSOPEN`, which a
login profile sets on most distributions, names a command it runs. `more` goes with it, being
the same program on many hosts. So `grep 'git commit' f | less` is denied where
`grep 'git commit' f` is not.

What counts is `git` and the subcommand standing as two whole words once the quoting is removed,
so `awk '/git commit/{print}'` runs — the `/` after the word breaks it — while
`sed -e 's|git commit|Y|g'` does not. A `$( … )`, a backtick or a `$(( … ))` anywhere in the
same command withdraws the exemption, since what a substitution prints is a command; put it in a
separate command and the reading tools are known again. So does an environment assignment in
front of one (`LC_ALL=C grep …`) — it reaches inside the program, which is how `LESSOPEN` makes
`less` run a command nobody wrote.

When the quote belongs to a different command, separating the two with `;`, `&&` or a newline is
enough — each part of a command list is read alone. When it is that command's own argument, the
deny is the one an unclassified commit gets: `/flow` classifies the work, and the command runs
once that tier's evidence exists.

If something else is still blocked, read the deny. Without python3 the gate cannot tell an
invocation from a mention and blocks rather than guess. Otherwise the host's copy of the gate
scripts is older than the plugin — re-run `/flow-init`.

## `/flow` stops on Dev work

The `superpowers@claude-plugins-official` plugin is missing. Install it
([README requirements](../../README.md#requirements)) and run `/flow` again; do not fall back to
implementing by hand.

## `/flow-init` ends on a gate problem

A run whose commit gate would not fire ends on one of these instead of a completion line:

| Message starts with | Cause | Fix |
|---------------------|-------|-----|
| `커밋 게이트가 쓰는 파일이 호스트에 없거나 손상됐습니다` | A copied script or the policy is missing or differs from the plugin | Resolve the `[!]` step above it, re-run `/flow-init` |
| `settings.json 을 읽지 못해` | `.claude/settings.json` does not parse, is not UTF-8, or is not an object | Repair the file, re-run `/flow-init` |
| `커밋 게이트가 settings.json 에 없습니다` | The hook is absent, altered, or under a matcher that does not cover `Bash` | Resolve the `[!]` step above it, re-run `/flow-init` |
| `settings.json 의 disableAllHooks 가 켜져 있어` | `disableAllHooks: true` switches every hook off | Remove the setting |

## The gate does nothing

Commits that should be blocked go through. Causes, in the order to check them:

1. **Missing shell tools.** The gate is bash and reads the command through `timeout`, `cat`,
   `grep`, `sed`, `awk` and `head`; without them it cannot read its input and passes. On Windows,
   install Git for Windows. Run `bash .claude/harness-tier/scripts/check-deps.sh`.
2. **The hook is not registered or does not fire.** Re-run `/flow-init` and read its last lines —
   it names a missing file, a missing hook, a matcher that skips `Bash`, or `disableAllHooks`.
3. **The policy file is missing.** Without `flow-tiers.yaml` the gate cannot classify and lets
   commits through by design; `/flow-init` restores it.
4. **A `tier` marker from another branch.** A marker written on a different branch neither
   classifies nor blocks the current one, so the commit passes; run `/flow` on this branch.
5. **The commit ran outside a Claude session.** Terminal, CI and GitHub commits never reach
   layer 2.
