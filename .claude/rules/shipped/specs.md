---
paths:
  - "flow-tiers.yaml"
  - "flow-config.example.yaml"
  - "hooks/*.sh"
  - "agents/*.md"
  - "skills/flow/**/*"
  - "skills/flow-init/**/*"
  - "skills/commit/**/*"
  - "skills/release-commit/**/*"
  - "skills/harness-init/**/*"
  - "skills/harness-authoring/**/*"
  - "scripts/flow_gate_check.py"
  - "scripts/_harness_paths.py"
  - "scripts/precommit-runner.sh"
  - "scripts/check-merge-ruleset.sh"
  - "scripts/finalize_prerelease.py"
  - "scripts/bump_version.py"
  - "scripts/wiki_graph.py"
  - "scripts/doc_style_check.py"
  - "scripts/harness_scaffold.py"
  - ".github/workflows/release.yml"
  - "github/release.*.yml"
---

# The shipped rule behind the file you are editing

`rules/` ships to consumers and nothing loads it here. Read the row's rule before changing the
file that pulled this one in: the rule is the specification that file implements. An `@` import
here would load that rule at session start, trigger or not — the pointer is what keeps it scoped.

| The file | Its rule |
|---|---|
| `flow-tiers.yaml` · `skills/flow` · `skills/commit` · `hooks/inject-risk-tiers.sh` · `scripts/flow_gate_check.py` | [`risk-tiers.md`](../../../rules/risk-tiers.md) |
| `scripts/precommit-runner.sh` · `scripts/wiki_graph.py` · `scripts/doc_style_check.py` · `hooks/invalidate-gate-markers.sh` · `flow-config.example.yaml` · `skills/flow-init` | [`gate-mechanics.md`](../../../rules/gate-mechanics.md) |
| the merge path in `scripts/flow_gate_check.py` · `scripts/_harness_paths.py` · `flow-tiers.yaml` `merge_strategy` | [`merge-strategy.md`](../../../rules/merge-strategy.md) |
| `skills/release-commit` · `scripts/check-merge-ruleset.sh` · `scripts/finalize_prerelease.py` · `scripts/bump_version.py` · the release workflows | [`promotion.md`](../../../rules/promotion.md) |
| `skills/harness-init` · `skills/harness-authoring` · `agents/` · `scripts/harness_scaffold.py` | [`harness-rules.md`](../../../rules/harness-rules.md) |

None of them governs this session: the workflow here is the installed vway-kit's, injected at
SessionStart. Where the two disagree, the file being edited follows `rules/`.
