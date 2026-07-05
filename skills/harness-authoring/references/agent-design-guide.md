# Agent Design Guide

The discipline `harness-authoring` follows when generating agents for the host project.
Condensed and adapted from [revfactory/harness](https://github.com/revfactory/harness) agent-design-patterns into the harness-tier tone.

## Core Principle

**One agent, one role.** The more focused it is, the higher its reusability and the less duplication. If it has more than one role, consider splitting it.

## 1. Split Criteria

| Criterion | Split | Merge |
|------|------|------|
| Expertise | when domains differ | when they overlap |
| Parallelism | when they can run independently | when sequentially dependent |
| Context | when the load is heavy | when light and fast |
| Reusability | when other teams use it too | when only this team uses it |

## 2. Reuse Design (Avoiding Duplication)

Before creating a new one, check for overlap with existing agents.

| Situation | Action |
|------|------|
| Existing one fully covers the new one | No new agent — reuse the existing one |
| Partial overlap and generalizable | Generalize/extend the existing one |
| Partial overlap that is intentionally domain-specific | Proceed with new (keep separate) |
| Scope is entirely different | Proceed with new |

Generalizing an existing agent can change the behavior of orchestrators that depend on it — check dependencies before extending, and dry-run afterward.

## 3. Agent Definition Structure

```markdown
---
name: agent-name
description: "1-2 sentence role + trigger keywords (pushy). <example>…</example> recommended."
tools: Read, Grep, Glob  # exclude write tools for a read-only role (omit for all tools). Declaration must match actual permissions
model: opus  # or remove
---

You are an expert [role] in [domain]. [Single responsibility].

## Core Role
1. …

## Working Principles
- …

## Input / Output Protocol
- Input: [what, from where]
- Output: [what, to where — file path·format]. **A read-only agent (tools = Read/Grep/Glob) cannot write** — it **returns** its output for the caller/leader to persist; declare that, not a self-write to a path it cannot reach (tool-fit — §4).

## Cross-Talk Protocol (optional — only when the Agent Teams experimental feature is on; omit for standard fan-out)
- Receive: [what message, from whom]
- Send: [what message, to whom]

## Error Handling
- [behavior on failure·timeout]
```

**Principle**: every agent is defined as a `.claude/agents/{name}.md` file (even a built-in type). Existing
as a file is what guarantees the reuse and collaboration protocols.

## 4. Choosing a Built-in Type

| Situation | Recommended | Reason |
|------|------|------|
| Read code only (analysis/review) | `Explore` | Prevents accidental file edits |
| Design/planning only | `Plan` | Focus on analysis, prevent changes |
| Web research·general-purpose | `general-purpose` | Full toolset including WebSearch/WebFetch |
| File-editing implementation | Custom type | Full toolset + specialized instructions |

**Enforce read-only**: even for a custom type, if the role is read-only like analysis or review, **restrict**
the frontmatter `tools` to read tools (`Read, Grep, Glob`). Even if the body says "does not modify any file," an
empty `tools` leaves write permissions in place, so the declaration diverges from actual permissions (a critic `tool-fit`
violation). If writes are not needed, always restrict.

## 5. Skill ↔ Agent Distinction / Linkage

- **Skill** = "how it is done" (procedure + tool bundle, `.claude/skills/`). **Agent** = "who does it" (persona, `.claude/agents/`).
- Linkage: if highly reusable, **call the Skill tool**; if short and dedicated, **inline it**; if large or conditional, **load a reference**.

## 6. Parallel Fan-out Default

With two or more agents, **parallel dispatch of `Agent` (formerly `Task`, alias) subagents (fan-out/fan-in, generate-verify) is the default**.
Only when inter-agent communication improves quality, and only on builds where the Agent Teams experimental feature (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
is enabled, use `SendMessage` cross-talk as an **option** (the deprecated `TeamCreate`/`TaskCreate`, etc. are forbidden).
Fill in the team communication protocol section only when cross-talk is possible.
