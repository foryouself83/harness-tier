#!/usr/bin/env python3
"""Build throwaway projects that put a skill's judgement under test, and print the
prompt + pass criteria for each.

`tests/skills/` proves a skill's *commands* work. It cannot prove the agent
reading the skill reaches the right conclusion — that needs a model. This script
supplies the other half: an isolated fixture whose correct answer is known in advance,
so a fresh agent's behaviour is checkable rather than merely plausible.

Every scenario is built so that the *wrong* answer is the tempting one. `custom-testdir`
is the regression that motivated this file: a project with a real suite under a
non-default `testDir`, where an agent that assumes `./tests` concludes "no tests" and
scaffolds over the suite. A green pytest run never noticed, because nothing executed the
skill's reasoning.

    python3 scripts/skill_sandbox.py --list
    python3 scripts/skill_sandbox.py custom-testdir          # build + print the prompt
    python3 scripts/skill_sandbox.py --all --out-dir /tmp/sb

Run the printed prompt in a *fresh* agent with no memory of this conversation —
context leak is what makes a skill look better than it is. Then score the transcript
against `expect` / `reject`.

**Coverage is deliberately partial.** A scenario is worth writing only where a throwaway
directory can create the state that decides the skill's answer. That covers /integration,
/playwright-scaffold, /performance, /doc-sync, /prose-review, /wiki-init and /design-table
(the heaviest /design-* path; its siblings follow the same procedure). The rest are
out of reach here, and adding hollow scenarios for them would report coverage this file
does not have:

* `/flow-init`, `/flow-uninstall` — their subject is the *host session*: a registered commit
  hook, an installed plugin cache, `${CLAUDE_PLUGIN_ROOT}`. A fixture directory cannot stand
  any of that up, and `tests/flow_gate/` and `tests/flow_init/` already cover the mechanics.
  `/flow` has one scenario for the single piece of its state a directory *can* create — a
  working tree with pending changes, which is what "commit these changes" presumes. What the
  fixture still cannot reach is everything after the routing decision: the registered hook,
  the marker it reads, the plugin cache.
* `/harness-init`, `/harness-authoring`, `/harness-deployments` — each fans out to
  sub-agents and the live web, so a run is neither cheap nor repeatable, and its output is
  prose whose correctness is a judgement rather than an assertion. `harness-critic` is the
  intended reviewer.
* `/harness-insight` — reads Claude Code transcripts from outside the repo, which a
  project fixture cannot supply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from _harness_paths import force_utf8_io  # direct execution (sibling)
except ImportError:
    from scripts._harness_paths import force_utf8_io  # package (test/dev)

REPO = Path(__file__).resolve().parent.parent


@dataclass
class Scenario:
    name: str
    skill: str
    why: str
    prompt: str
    expect: list[str]
    reject: list[str]
    files: dict[str, str] = field(default_factory=dict)
    dirs: list[str] = field(default_factory=list)
    # { "<relpath in the fixture>": "<relpath in this repo>" } — files copied verbatim
    # instead of written inline, for the gate scripts a host gets from /flow-init. A skill
    # that runs one by its documented host path needs it to be there; inlining a
    # 900-line script as a string would go stale the moment the real one changes.
    copy_from_repo: dict[str, str] = field(default_factory=dict)
    # Seed the fixture as a git repository with everything committed. For a skill that reads
    # git state — wiki-init builds the graph from the index — a bare directory measures the
    # fallback path instead of the real one. Off by default: `git init` costs a subprocess
    # per build, and no other scenario's answer depends on it.
    git: bool = False
    # Written after the seed commit, so the built fixture has a dirty working tree: the same
    # { "<relpath>": "<content>" } shape as `files`, and a path already in `files` is modified
    # rather than added. A prompt about pending changes has none to reach for otherwise —
    # `git` commits everything the scenario wrote.
    uncommitted: dict[str, str] = field(default_factory=dict)
    # Machine-checkable golden end-state for the outcome arm (evals/outcome.py). The prose
    # expect/reject above stay for the human-judged invocation sandbox; this is asserted.
    # { "<relpath>": {"must_contain": [...], "must_not_contain": [...]} }
    outcome: dict[str, dict[str, list[str]]] = field(default_factory=dict)


PLAYWRIGHT_CONFIG_E2E = """\
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://localhost:5173' },
});
"""

PLAYWRIGHT_CONFIG_DEFAULT = """\
import { defineConfig } from '@playwright/test';
export default defineConfig({
  use: { baseURL: 'http://localhost:3000' },
});
"""

SPEC = """\
import { test, expect } from '@playwright/test';
test('placeholder', async ({ page }) => { await page.goto('/'); });
"""

WEB_PACKAGE_JSON = json.dumps(
    {
        "name": "sandbox-web",
        "devDependencies": {"@playwright/test": "^1.48.0", "vite": "^5.0.0"},
        "dependencies": {"react": "^18.3.0"},
    },
    indent=2,
)

CLI_PACKAGE_JSON = json.dumps(
    {"name": "sandbox-cli", "bin": {"sbx": "./bin/sbx.js"}, "dependencies": {}}, indent=2
)

# The sentence the wiki-init golden tracks. It sits in one of `docs/backend.md`'s two H2
# sections, so where it ends up says whether the document was split or merely stamped with
# front matter: a correct run leaves a link in its place, and the claim itself moves to the
# node about authentication. One sentence rather than the whole section on purpose —
# a reformatted block would slip a multi-line needle and read as a pass.
WIKI_JWT_CLAIM = "Access tokens expire after 15 minutes."

WIKI_BACKEND_DOC = f"""\
# Backend

## JWT authentication

{WIKI_JWT_CLAIM} Refresh tokens live for 30 days and rotate on every use, so a
stolen refresh token is usable once.

## Postgres schema

`users` owns the identity columns; `sessions` holds one row per refresh token and
cascades on delete.
"""

# Every failure the prose rule names, in one file: a header carrying an author tag, a change
# log and a revision date; two comments that paraphrase the line under them; a docstring that
# explains how; and a line anchor into another file. The comment marks and quotes here are
# fixture bytes, not this module's own prose — a string literal is code to `python_prose`.
PROSE_REVIEW_MODULE = '''"""Order pricing.

@author  j.doe
Last updated: 2026-08-14
Changelog:
  2026-08-14  split the discount table out of price()
  2026-07-02  first cut
"""

DISCOUNTS = {"gold": 0.2, "silver": 0.1}


def discount_for(tier):
    """Look the tier up in DISCOUNTS and return what is there.

    Does a dict lookup, falling back to 0.0 when the key is absent.
    """
    # read the discount out of the dict
    return DISCOUNTS.get(tier, 0.0)


def price(amount, tier):
    # multiply the amount by one minus the discount
    net = amount * (1 - discount_for(tier))
    # round to two places, the same way billing/invoice.py:118 does
    return round(net, 2)
'''

# A shop host for /design-table: an SRS with two FRs, an SDS mapping both, an ERD that
# already issued ENT-001/ENT-002, and a schema whose orders table points at users. The
# ERD is written in the shipped erd template's shape so the cross-check runs, not skips.
DESIGN_SRS_README = """\
---
wiki_id: srs.readme
title: Shop SRS
tags: [srs]
---
# Shop SRS

## 4. Customer Requirements

<a id="c-001"></a>**C-001** Customers buy from the shop online.
"""

DESIGN_SRS_ORDER = """\
---
wiki_id: srs.order
title: Orders
tags: [srs]
---
# Orders

<a id="fr-order-001"></a>**FR-ORDER-001** A visitor signs up. (← [C-001](README.md#c-001))

<a id="fr-order-002"></a>**FR-ORDER-002** A user places an order. (← [C-001](README.md#c-001))
"""

DESIGN_SDS = """\
---
wiki_id: sds.readme
title: Shop SDS
tags: [sds]
sources: {}
---
# Shop SDS

## Module Overview

#### accounts
- Implemented requirements: [FR-ORDER-001](../srs/order.md#fr-order-001)
- Owned data: users

#### ordering
- Implemented requirements: [FR-ORDER-002](../srs/order.md#fr-order-002)
- Owned data: orders
"""

DESIGN_ERD = """\
---
wiki_id: deliverables.erd
title: ERD
tags: [deliverable, erd]
related: [srs.readme]
sources: {app/models.py: null}
revisions:
  - {version: "1.0", date: 2026-09-21, summary: first}
---
## 1. 개요

Shop accounts and orders.

## 2. 엔터티 관계도

```mermaid
erDiagram
  USER ||--o{ ORDER : places
```

## 3. 엔터티 목록

| 엔터티ID | 엔터티명 | 설명 | 주 식별자 | 요구사항 |
|---|---|---|---|---|
| <a id="ent-001"></a>ENT-001 | User | account | id | FR-ORDER-001 |
| <a id="ent-002"></a>ENT-002 | Order | order | id | FR-ORDER-002 |

## 4. 관계 정의

| 부모 엔터티 | 자식 엔터티 | 카디널리티 | 관계 설명 |
|---|---|---|---|
| ENT-001 | ENT-002 | 1:N | a user places orders |

## 5. 요구사항 추적표

| 요구사항 | 엔터티 |
|---|---|
| FR-ORDER-001 | ENT-001 |
| FR-ORDER-002 | ENT-002 |

## 부록 A. 코드 인벤토리

```bash
grep -n "class .*(Base)" app/models.py
```

| 대상 | 근거 | 문서 ID |
|---|---|---|
| User | app/models.py | ENT-001 |
| Order | app/models.py | ENT-002 |
"""

DESIGN_MODELS = """\
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total = Column(Integer, nullable=False)
"""

DESIGN_MIGRATION = """\
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  total INTEGER NOT NULL
);
"""

# Everything /flow-init would have put on the host for the /design-* skills: the checker
# and its imports, and the seeded templates the check reads.
DESIGN_HOST_COPIES = {
    **{
        f".claude/harness-tier/scripts/{name}": f"scripts/{name}"
        for name in (
            "_harness_paths.py",
            "_md_anchors.py",
            "_design_md.py",
            "srs_check.py",
            "wiki_graph.py",
            "design_doc_check.py",
            "design_doc_render.py",
        )
    },
    **{
        f".claude/harness-tier/templates/design-docs/{doc}.template.md": (
            f"templates/design-docs/{doc}.template.md"
        )
        for doc in ("srs", "sds", "architecture", "api", "erd", "table")
    },
}


SCENARIOS: list[Scenario] = [
    Scenario(
        name="custom-testdir",
        skill="integration",
        why=(
            "The suite lives under a non-default testDir. An agent that assumes ./tests "
            "reports zero cases and scaffolds a starter smoke over a real suite — the "
            "exact regression this fixture exists to catch."
        ),
        prompt="Run integration verification on this project and report the result.",
        expect=[
            "reads testDir from playwright.config (resolves it to ./e2e)",
            "finds the 2 existing cases under e2e/",
            "runs / attempts to run the existing suite",
        ],
        reject=[
            "reports zero cases",
            "invokes playwright-scaffold or generates main.smoke.spec",
            "searches ./tests without first resolving testDir",
        ],
        files={
            "playwright.config.ts": PLAYWRIGHT_CONFIG_E2E,
            "package.json": WEB_PACKAGE_JSON,
            "e2e/checkout.spec.ts": SPEC,
            "e2e/auth.spec.ts": SPEC,
            "index.html": "<!doctype html><title>sandbox</title>\n",
        },
    ),
    Scenario(
        name="empty-web",
        skill="integration",
        why=(
            "Web project, zero cases. Zero must stay reachable: this is the one state "
            "where scaffolding is correct, so a fix for custom-testdir that simply never "
            "scaffolds would pass that test and fail here."
        ),
        prompt="Run integration verification on this project and report the result.",
        expect=[
            "detects the project as a web frontend",
            "finds zero existing cases",
            "reaches for playwright-scaffold to generate a main-screen smoke",
            "asks the user to confirm the baseURL rather than assuming one",
        ],
        reject=[
            "invents user scenarios (login, checkout) instead of a main-screen smoke",
            "asserts a baseURL without asking",
        ],
        files={
            "playwright.config.ts": PLAYWRIGHT_CONFIG_DEFAULT,
            "package.json": WEB_PACKAGE_JSON,
            "index.html": "<!doctype html><title>sandbox</title>\n",
        },
        dirs=["tests"],
    ),
    Scenario(
        name="misconfigured-testdir",
        skill="integration",
        why=(
            "The config points testDir at a directory that does not exist. Suppressing "
            "find's stderr renders that identically to 'the directory is there and empty' "
            "— and empty is what authorises scaffolding. The right answer is to report "
            "the misconfiguration, not to generate a spec into a path Playwright is not "
            "even looking at."
        ),
        prompt="Run integration verification on this project and report the result.",
        expect=[
            "resolves testDir to ./e2e from the config",
            "notices ./e2e does not exist",
            "reports it as a misconfiguration",
        ],
        reject=[
            "concludes 'zero cases' and scaffolds",
            "silently creates ./e2e and generates a spec into it",
            "reports the project as having no tests without mentioning the missing directory",
        ],
        files={
            "playwright.config.ts": PLAYWRIGHT_CONFIG_E2E,
            "package.json": WEB_PACKAGE_JSON,
            "index.html": "<!doctype html><title>sandbox</title>\n",
        },
    ),
    Scenario(
        name="frameworkless-web",
        skill="integration",
        why=(
            "A plain web app: index.html plus a bundler, no framework in the allowlist. "
            "Keying the verdict on the allowlist alone files it as non-web and hands a "
            "perfectly automatable browser app to a human."
        ),
        prompt="Run integration verification on this project and report the result.",
        expect=[
            "classifies the project as web on the supporting signals (index.html / vite.config)",
            "proceeds down the Playwright path",
        ],
        reject=[
            "classifies it as non-web because no allowlist dependency matched",
            "asks the user for manual scenarios",
        ],
        files={
            "package.json": json.dumps(
                {"name": "vanilla", "devDependencies": {"vite": "^5.0.0"}}, indent=2
            ),
            "vite.config.js": "export default { server: { port: 5173 } };\n",
            "index.html": "<!doctype html><title>vanilla</title>\n",
            "src/main.js": "document.body.textContent = 'hi';\n",
        },
    ),
    Scenario(
        name="flow-pending-commit",
        skill="flow",
        why=(
            "A repository with a real pending change, which is what a bare 'commit these "
            "changes' presumes. In an empty directory that request has no answer, so the "
            "session reads an empty tree and replies instead of routing — a miss that says "
            "nothing about the description."
        ),
        prompt="Commit these changes.",
        expect=[
            "classifies the tier before it commits",
            "records the tier marker the commit gate reads",
        ],
        reject=[
            "commits without classifying the work",
            "reports that there is nothing to commit",
        ],
        files={
            "README.md": "# sbx\n\nA tiny CLI.\n",
            "sbx/__init__.py": "",
            "sbx/cli.py": "def main(argv):\n    print(argv)\n    return 0\n",
            "tests/test_cli.py": (
                "from sbx.cli import main\n\n\ndef test_main():\n    assert main([]) == 0\n"
            ),
        },
        git=True,
        uncommitted={
            "sbx/cli.py": (
                "def main(argv):\n"
                "    if not argv:\n"
                '        print("usage: sbx <name>")\n'
                "        return 2\n"
                "    print(argv)\n"
                "    return 0\n"
            ),
            "tests/test_cli.py": (
                "from sbx.cli import main\n\n\n"
                "def test_main():\n    assert main([]) == 2\n\n\n"
                'def test_main_with_a_name():\n    assert main(["x"]) == 0\n'
            ),
        },
    ),
    Scenario(
        name="non-web-cli",
        skill="integration",
        why=(
            "A CLI has a `bin` field and no web framework. The skill routes non-web to a "
            "human, so an agent that reaches for Playwright here has followed the "
            "description's web wording past the body's detection table."
        ),
        prompt="Run integration verification on this project and report the result.",
        expect=[
            "classifies the project as non-web (CLI)",
            "asks the user for scenarios and pass criteria",
        ],
        reject=[
            "installs or runs Playwright",
            "generates a smoke test",
        ],
        files={
            "package.json": CLI_PACKAGE_JSON,
            "bin/sbx.js": "#!/usr/bin/env node\nconsole.log('hi');\n",
        },
    ),
    Scenario(
        name="scaffold-idempotent",
        skill="playwright-scaffold",
        why=(
            "A previous run already left main.smoke.spec.ts. Regenerating would clobber "
            "any edits made to it since."
        ),
        prompt="Generate a main-screen smoke test for this project.",
        expect=[
            "detects the existing main.smoke.spec.ts",
            "reports and stops without writing",
        ],
        reject=[
            "overwrites or regenerates main.smoke.spec.ts",
        ],
        files={
            "playwright.config.ts": PLAYWRIGHT_CONFIG_E2E,
            "package.json": WEB_PACKAGE_JSON,
            "e2e/main.smoke.spec.ts": SPEC,
        },
    ),
    Scenario(
        name="scaffold-baseurl-unknown",
        skill="playwright-scaffold",
        why=(
            "The config has no baseURL and the codebase offers two conflicting ports "
            "(compose says 8080, the dev script says 5173). The skill forbids asserting "
            "a guess, so the agent must ask."
        ),
        prompt="Generate a main-screen smoke test for this project.",
        expect=[
            "gathers baseURL candidates from the codebase (8080 and/or 5173)",
            "asks the user to confirm which baseURL is right",
            "adds use.baseURL to the existing playwright.config.ts — edits it, does not replace it",
        ],
        reject=[
            "picks a port and states it as fact without asking",
            "scaffolds a fresh config over the existing one",
        ],
        files={
            "package.json": json.dumps(
                {
                    "name": "sandbox-web",
                    "scripts": {"dev": "vite --port 5173"},
                    "devDependencies": {"@playwright/test": "^1.48.0", "vite": "^5.0.0"},
                    "dependencies": {"react": "^18.3.0"},
                },
                indent=2,
            ),
            "docker-compose.yml": 'services:\n  web:\n    ports:\n      - "8080:80"\n',
            "index.html": "<!doctype html><title>sandbox</title>\n",
            # The state the `why` above describes — a config that EXISTS without a baseURL.
            # Without this file the scenario exercised Step 4's config-absent row while
            # claiming to test the edit-not-replace row, which therefore had no fixture.
            "playwright.config.ts": (
                "import { defineConfig } from '@playwright/test';\n"
                "export default defineConfig({ testDir: './tests' });\n"
            ),
        },
    ),
    Scenario(
        name="scaffold-ts-without-tsconfig",
        skill="playwright-scaffold",
        why=(
            "`@playwright/test` bundles its own TypeScript, so a TS Playwright project "
            "routinely has neither a tsconfig.json nor a typescript dependency. Keying the "
            "language on those two alone drops a .js spec into a .ts suite. This fixture "
            "is the shape that surfaced the gap."
        ),
        prompt="Generate a main-screen smoke test for this project.",
        expect=[
            "generates a .spec.ts (playwright.config.ts is itself the TypeScript signal)",
        ],
        reject=[
            "generates a .spec.js because tsconfig.json and a typescript dependency are absent",
        ],
        files={
            "playwright.config.ts": PLAYWRIGHT_CONFIG_E2E,
            "package.json": WEB_PACKAGE_JSON,
            "index.html": "<!doctype html><title>sandbox</title>\n",
        },
        dirs=["e2e"],
    ),
    Scenario(
        name="perf-n-plus-one",
        skill="performance",
        why=(
            "A textbook Django N+1 inside a loop, plus a select_related fix available. The "
            "skill flags statically and delegates the verdict to a runtime tool — an agent "
            "that declares a measured regression has overclaimed from a grep."
        ),
        prompt="Run a performance check on this project.",
        expect=[
            "detects the Python stack",
            "flags the N+1 in views.py",
            "marks it 'needs review' / delegates the final verdict to a runtime tool",
            "runs the language-agnostic complexity check as well",
        ],
        reject=[
            "reports measured latency or a confirmed query count from static analysis alone",
            "runs a load test (there is no OpenAPI spec and no running backend here)",
        ],
        files={
            "pyproject.toml": '[project]\nname = "sandbox"\nversion = "0.1.0"\n',
            "app/views.py": (
                "def index(request):\n"
                "    users = User.objects.all()\n"
                "    return [u.profile.name for u in users]  # N+1: profile per user\n"
            ),
            "app/models.py": (
                "class Profile(models.Model):\n"
                "    name = models.CharField(max_length=100)\n\n"
                "class User(models.Model):\n"
                "    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)\n"
            ),
            # The eval's happy set asks about a re-rendering table; without a frontend file
            # the fixture falsified that prompt's premise and the miss was scored against
            # the description. A fresh object and closure per row per render is the flag.
            "frontend/Table.jsx": (
                "export function Table({ rows }) {\n"
                "  return rows.map((r) => (\n"
                "    <Row key={r.id} style={{ padding: 4 }} onClick={() => select(r)} />\n"
                "  ));\n"
                "}\n"
            ),
        },
    ),
    Scenario(
        name="doc-sync-drift",
        skill="doc-sync",
        why=(
            "The code says port 9090; two docs disagree with it and with each other. The "
            "skill's job is to pick the SSOT and reduce the rest to it, not to pick a "
            "majority or rewrite the code."
        ),
        # The second clause stands in for the tier confirmation /flow's Phase 2 asks a human
        # for, as wiki-init's prompt pre-answers its Steps 3 and 5. Without it a headless session
        # that honours the gate stops before editing and fails, while one that skips the gate
        # passes, so the score would reward skipping it. Which file is the SSOT stays the
        # agent's judgement.
        prompt=(
            "The port changed. Sync the documentation — it is a docs-only change, so go ahead "
            "without asking me to confirm the tier."
        ),
        expect=[
            "spots the port disagreement across .env.example, README.md and docs/api.md",
            "treats the code/.env.example as the source of truth (9090)",
            "reports what it changed and why",
        ],
        reject=[
            "edits app/server.py to match the docs",
            "leaves two docs stating different ports",
        ],
        files={
            ".env.example": "PORT=9090\n",
            "app/server.py": "PORT = 9090\n\ndef serve():\n    return PORT\n",
            "README.md": "# Sandbox\n\nThe server listens on port 8080.\n",
            "docs/api.md": "# API\n\nBase URL: `http://localhost:3000`\n",
        },
        outcome={
            "README.md": {"must_contain": ["9090"], "must_not_contain": ["8080"]},
            "docs/api.md": {"must_contain": ["9090"], "must_not_contain": ["3000"]},
            # server.py must keep 9090: the scenario's reject forbids rewriting code to docs.
            "app/server.py": {"must_contain": ["9090"]},
        },
    ),
    Scenario(
        name="prose-review-comments",
        skill="prose-review",
        why=(
            "Both comments in app/pricing.py restate the line under them, the docstring "
            "explains how, and the module header carries an author tag, a changelog and a "
            "revision date. The tempting answer is to reword all of it into better prose; the "
            "rule's answer is that most of it should not exist and the header belongs to git."
        ),
        prompt=(
            "Go over the comments and docstrings in app/pricing.py and bring them in line "
            "with the project's prose rules."
        ),
        expect=[
            "deletes the comments that paraphrase the line beneath them rather than rewording",
            "strips the author tag, the changelog and the date out of the module docstring",
            "keeps the billing filename and drops the line number appended to it",
            "cuts the how-explanation from the docstring and keeps what the code cannot say",
        ],
        reject=[
            "rewrites a self-evident comment into a better sentence and keeps it",
            "keeps the revision header because it reads as useful",
            "changes a line of code while rewriting the prose",
        ],
        files={
            "app/pricing.py": PROSE_REVIEW_MODULE,
            "README.md": "# Pricing\n\nTier discounts are applied before rounding.\n",
        },
    ),
    Scenario(
        name="wiki-init-migration",
        skill="wiki-init",
        why=(
            "docs/backend.md holds two concepts under two H2s. The tempting answer is to "
            "stamp front matter on it and move on — every structural rule still passes, so "
            "--verify is silent, and the wiki is useless because --neighbors then hands the "
            "model a blob covering both subjects. docs/deploy.md is the opposite trap: with "
            "no H2 at all, splitting it would be wrong."
        ),
        # /wiki-init is disable-model-invocation, so the slash command IS the prompt — there
        # is no description for the model to match on. The two clauses stand in for the
        # answers Steps 3 and 5 ask a human for; the judgement they gate (what to split, how
        # ids derive, which relations to write) stays the agent's.
        prompt=(
            "/wiki-init — migrate every candidate document, and go with the relationships "
            "you propose rather than waiting on me to confirm them."
        ),
        expect=[
            "splits docs/backend.md by its two H2s and leaves a link in each section's place",
            "keeps the original as a node too, with related pointing at what came out of it",
            "leaves docs/deploy.md whole — no H2 means nothing to split",
            "derives each wiki_id from the path relative to docs/, and never writes used_by",
            "turns wiki.enable on before building, so --build is not a no-op",
        ],
        reject=[
            "gives docs/backend.md front matter without splitting it",
            "deletes docs/backend.md after moving its sections out",
            "writes used_by or defects by hand",
            "leaves the new ids out of the index's related list",
        ],
        files={
            ".claude/harness-tier/config/flow-config.yaml": (
                "branches:\n"
                "  integration: dev\n"
                "  staging: stage\n"
                "  production: main\n"
                "wiki:\n"
                "  enable: false\n"
                "  root: docs/\n"
                "  index: docs/index.md\n"
                "  max_lines: 400\n"
                "  context_lines: 2000\n"
                "  defect_rule_threshold: 3\n"
            ),
            "docs/index.md": "# Docs\n\n- [Backend](backend.md)\n- [Deploy](deploy.md)\n",
            "docs/backend.md": WIKI_BACKEND_DOC,
            "docs/deploy.md": "# Deploy\n\nPush to main; the release workflow does the rest.\n",
            "app/auth.py": "ACCESS_TTL_MIN = 15\nREFRESH_TTL_DAYS = 30\n",
            "app/db.py": "TABLES = ('users', 'sessions')\n",
        },
        # Step 8 runs this by its literal host path. /flow-init is what puts it there on a
        # real host; without it every run fails that command and the score measures how
        # well the agent guessed a substitute path.
        copy_from_repo={
            ".claude/harness-tier/scripts/wiki_graph.py": "scripts/wiki_graph.py",
            ".claude/harness-tier/scripts/_harness_paths.py": "scripts/_harness_paths.py",
        },
        # The graph is built from git's index, so the documents have to be tracked.
        git=True,
        outcome={
            # Split, not stamped: the claim moved out and a link took its place. `related:`
            # is what separates a split from a deletion — Step 4 keeps the original as a
            # node pointing at everything that came out of it, so a run that dropped
            # the section would otherwise satisfy the must_not_contain above.
            "docs/backend.md": {
                "must_contain": ["wiki_id:", "related:"],
                "must_not_contain": [WIKI_JWT_CLAIM, "used_by:"],
            },
            # The zero-H2 branch: still a node, still not split, still no generated edge.
            "docs/deploy.md": {"must_contain": ["wiki_id:"], "must_not_contain": ["used_by:"]},
            # Orphan detection reads front-matter edges only — a body link list is not
            # enough, and an empty `related: []` is the shape that silently disables it.
            "docs/index.md": {"must_contain": ["wiki_id:", "related:", "backend", "deploy"]},
            # Ids are asserted here rather than in the documents: this file is written by
            # yaml.safe_dump, so its shape is fixed, while an author may legitimately quote
            # a scalar in front matter. The generated header is the load-bearing needle —
            # it is the one string a hand-written stub will not have, so it proves --build
            # ran, which in turn proves Step 7 ran (--build no-ops on a disabled
            # wiki and would leave nothing here at all).
            "docs/graph/graph.yaml": {
                "must_contain": ["GENERATED by wiki_graph.py", "nodes:", "backend", "deploy"]
            },
            # Step 7 says touch only the `wiki` key: a rewrite that drops the rest of the
            # host's config is not a migration, it is collateral damage.
            ".claude/harness-tier/config/flow-config.yaml": {
                "must_contain": ["enable: true", "integration: dev"]
            },
        },
    ),
    Scenario(
        name="design-table-shop",
        skill="design-table",
        why=(
            "The ERD already issued ENT-001/ENT-002 and the schema's orders table points at "
            "users. The tempting answers invent entity names, copy the template's {{...}} "
            "slots through, or hand-type a wiki_id — the golden asserts against those. An FK "
            "cell left as a column name passes every substring needle, so that trap is "
            "judged by expect alone."
        ),
        # /design-table is disable-model-invocation, so the slash command IS the prompt. The
        # clause answers Step 1's install question: the outcome is the Markdown, and a
        # headless session cannot answer AskUserQuestion.
        prompt=(
            "/design-table — do not install anything; if the render dependencies are "
            "missing, run the check steps and skip rendering."
        ),
        expect=[
            "issues one TBL block per schema table, users and orders",
            "names ENT-001 and ENT-002 from erd.md in the entity column",
            "puts the users table's TBL id in the orders FK column",
            "records the listing command and one inventory row per table",
            "takes wiki_id from --wiki-id and runs --doc table until it reports 0 violations",
        ],
        reject=[
            "invents entities the ERD does not issue",
            "leaves a {{...}} template slot in the document",
            "edits the template or erd.md to make the check pass",
        ],
        files={
            "docs/srs/README.md": DESIGN_SRS_README,
            "docs/srs/order.md": DESIGN_SRS_ORDER,
            "docs/sds/README.md": DESIGN_SDS,
            "docs/deliverables/erd.md": DESIGN_ERD,
            "app/models.py": DESIGN_MODELS,
            "migrations/001_init.sql": DESIGN_MIGRATION,
        },
        copy_from_repo=DESIGN_HOST_COPIES,
        outcome={
            # Both tables issued, both entities mapped, the derived id used (value only: an
            # author may quote the scalar), the listing command kept, no template slot left.
            "docs/deliverables/table.md": {
                "must_contain": [
                    "wiki_id:",
                    "deliverables.table",
                    "tbl-001",
                    "tbl-002",
                    "ENT-001",
                    "ENT-002",
                    "```bash",
                ],
                "must_not_contain": ["{{"],
            },
            # The checker's inputs stay the consumer's: a run that edited them to pass
            # would drop the ERD's ids.
            "docs/deliverables/erd.md": {"must_contain": ["ent-001", "ent-002"]},
        },
    ),
]

BY_NAME = {s.name: s for s in SCENARIOS}


def _force_remove(func, path, _exc):
    """rmtree callback: clear the read-only bit and retry.

    Git writes its object files read-only, so on Windows a plain rmtree over a seeded
    fixture dies with PermissionError — which would make `--all --out-dir <dir>` work once
    and fail every time after."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


# Scenario fields that describe the run for a human instead of shaping it: the sandbox's
# prose pass/fail criteria and the rationale behind them. Nothing build() or check_outcome
# touches, so rewording one must not cost a re-measurement. Everything else is fingerprinted,
# including fields added later — see fingerprint. The cost runs the other way too: a field
# only the outcome arm reads (`outcome`, the sandbox `prompt`) still stales the invocation
# score of every skill whose cases run in that scenario.
SHA_EXEMPT = frozenset({"why", "expect", "reject"})


def _copied_file_sha(src: str) -> str:
    """Digest of one file `copy_from_repo` brings into the fixture.

    Line endings are normalized first. The checkout is CRLF on Windows and LF on the CI
    runner, so a digest over raw bytes fingerprints the checkout rather than the content, and
    the two platforms permanently disagree about the same file — every other input reaches
    the payload through read_text, which already normalizes.

    A path that does not resolve still fingerprints, under its own name: such a scenario is
    already broken and build() is where that gets said, while fingerprint is walked
    field-by-field by the tests, so raising here would turn a fingerprint into a crash."""
    try:
        content = (REPO / src).read_bytes()
    except (OSError, TypeError, ValueError):
        return "unreadable"
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def fingerprint(scenario: Scenario) -> dict:
    """The fixture content a measurement depends on, as a JSON-ready dict.

    Shared by both freshness keys — the outcome arm's `outcome_sha` and the invocation
    arm's `fixture_sha` — so a fixture edit stales every score that ran against it, and a
    prose edit (SHA_EXEMPT) stales none."""
    fixture = {k: v for k, v in asdict(scenario).items() if k not in SHA_EXEMPT}
    # A field added after a baseline was recorded stales every scenario that never sets it,
    # and the re-measure that clears it proves nothing — the fixture did not change. So a
    # later field drops out of the payload while it is unset, and joins it the moment a
    # scenario uses one. Every field present when the baselines were recorded stays in
    # unconditionally, empty or not, or their fingerprints would move instead.
    if not scenario.uncommitted:
        fixture.pop("uncommitted", None)
    fixture["copy_from_repo"] = {
        dest: [src, _copied_file_sha(src)] for dest, src in scenario.copy_from_repo.items()
    }
    return fixture


def build(scenario: Scenario, root: Path) -> Path:
    target = root / scenario.name
    if target.exists():
        # onerror, not onexc: the latter is Python 3.12+, and this file runs on the gate's
        # 3.8 floor. onerror is deprecated there but still honoured.
        shutil.rmtree(target, onerror=_force_remove)
    target.mkdir(parents=True)
    for rel in scenario.dirs:
        (target / rel).mkdir(parents=True, exist_ok=True)
    for rel, content in scenario.files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" keeps LF on Windows: a stray CR turns a resolved testDir into a
        # directory that does not exist, which would read as a skill bug.
        path.write_text(content, encoding="utf-8", newline="")
    for rel, src in scenario.copy_from_repo.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / src, dest)
    if scenario.git:
        # -c rather than `git config`: a fixture must not depend on the runner's global
        # identity, and must not write one either. gpgsign and hooksPath are neutralised for
        # the same reason with more teeth — a developer with global commit signing would hit
        # a pinentry prompt that hangs every session, and a global hooksPath would run their
        # hooks against a throwaway directory.
        identity = [
            "-c",
            "user.email=s@s",
            "-c",
            "user.name=S",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=",
        ]
        for cmd in (
            ["git", "init", "-q"],
            ["git", "add", "-A"],
            ["git", *identity, "commit", "-qm", "seed"],
        ):
            subprocess.run(cmd, cwd=target, check=True, capture_output=True)
    for rel, content in scenario.uncommitted.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
    return target


def check_outcome(scenario: Scenario, built: Path) -> tuple[bool, list[str]]:
    """Assert a built fixture reached the scenario's golden end-state.

    Deterministic substring checks per file — the SWE-bench-style score for the outcome arm.
    A missing file is a failure, not a crash: an agent that deleted or renamed the doc it was
    asked to sync did not reach the end-state either."""
    failures: list[str] = []
    for rel, spec in scenario.outcome.items():
        path = built / rel
        if not path.exists():
            failures.append(f"{rel}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in spec.get("must_contain", []):
            if needle not in text:
                failures.append(f"{rel}: missing {needle!r}")
        for needle in spec.get("must_not_contain", []):
            if needle in text:
                failures.append(f"{rel}: still contains {needle!r}")
    return not failures, failures


def render(scenario: Scenario, path: Path) -> str:
    lines = [
        "=" * 78,
        f"SCENARIO  {scenario.name}   (skill under test: /{scenario.skill})",
        "=" * 78,
        f"WHY       {scenario.why}",
        "",
        f"SANDBOX   {path}",
        "",
        "PROMPT    Run this in a fresh agent, cwd = the sandbox above:",
        "",
        f"    {scenario.prompt}",
        "",
        "PASS when the agent:",
    ]
    lines += [f"    [+] {e}" for e in scenario.expect]
    lines += ["", "FAIL if the agent:"]
    lines += [f"    [-] {r}" for r in scenario.reject]
    lines += [""]
    return "\n".join(lines)


def main() -> int:
    force_utf8_io()
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("scenario", nargs="?", help="scenario name (see --list)")
    ap.add_argument("--all", action="store_true", help="build every scenario")
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    ap.add_argument("--out-dir", help="where to build (default: a temp dir)")
    args = ap.parse_args()

    if args.list:
        for s in SCENARIOS:
            # Split on ". " (sentence boundary), not "." — three of the rationales carry
            # filenames (index.html, main.smoke.spec.ts, tsconfig.json) and a bare-dot
            # split cut them mid-name.
            first = s.why.split(". ")[0].rstrip(".")
            print(f"{s.name:26} /{s.skill:20} {first}.")
        return 0

    if args.all:
        chosen = SCENARIOS
    elif args.scenario:
        if args.scenario not in BY_NAME:
            print(f"unknown scenario {args.scenario!r}; try --list", file=sys.stderr)
            return 2
        chosen = [BY_NAME[args.scenario]]
    else:
        ap.print_help()
        return 2

    root = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="skill-sandbox-"))
    root.mkdir(parents=True, exist_ok=True)

    # No --json twin: nothing consumed it (run.py imports build()/BY_NAME directly, the
    # tests never invoke this CLI), and it duplicated the Scenario field list by hand.
    for s, p in [(s, build(s, root)) for s in chosen]:
        print(render(s, p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
