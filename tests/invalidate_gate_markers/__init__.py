"""The PostToolUse hook that voids the review/doc-sync evidence on an edit.

Deleting is the safe direction: a marker that should have survived costs a re-run, while one
that should have gone lets an unreviewed commit through. So every case this hook cannot decide
deletes, and what is spared is a path with no evidence above it. Everything about the hook itself is
FAIL-OPEN — no project dir, no evidence dir, an unreadable payload: exit 0, markers untouched,
the gate keeps whatever answer it already had.
"""
