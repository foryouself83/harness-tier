#!/usr/bin/env python3
"""Build throwaway projects that put a skill's judgement under test, and print the
prompt + pass criteria for each.

`tests/test_skills.py` proves a skill's *commands* work. It cannot prove the agent
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
/playwright-scaffold, /performance and /doc-sync. The rest are out of reach here, and
adding hollow scenarios for them would report coverage this file does not have:

* `/flow`, `/flow-init`, `/flow-uninstall` — their subject is the *host session*: a
  registered commit hook, an installed plugin cache, `${CLAUDE_PLUGIN_ROOT}`. A fixture
  directory cannot stand any of that up, and `tests/test_flow_gate_check.py` and
  `tests/test_flow_init_setup.py` already cover the mechanics.
* `/harness-init`, `/harness-authoring`, `/harness-deployments` — each fans out to
  sub-agents and the live web, so a run is neither cheap nor repeatable, and its output is
  prose whose correctness is a judgement rather than an assertion. `harness-critic` is the
  intended reviewer.
* `/harness-insight` — reads Claude Code transcripts from outside the repo, which a
  project fixture cannot supply.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


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
        prompt="The port changed. Sync the documentation.",
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
    ),
]

BY_NAME = {s.name: s for s in SCENARIOS}


def build(scenario: Scenario, root: Path) -> Path:
    target = root / scenario.name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for rel in scenario.dirs:
        (target / rel).mkdir(parents=True, exist_ok=True)
    for rel, content in scenario.files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" keeps LF on Windows: a stray CR turns a resolved testDir into a
        # directory that does not exist, which would read as a skill bug.
        path.write_text(content, encoding="utf-8", newline="")
    return target


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
