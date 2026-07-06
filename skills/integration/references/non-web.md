# Non-Web Integration Testing — human-in-the-loop + Reference OSS

> For non-web projects, integration-test automation is **not enforced**.
> This document covers per-type detection signals, the human-in-the-loop procedure, and freely
> choosable reference OSS (all Apache-2.0).

---

## 1. Per-Type Non-Web Signals

| Type | Detection signal | Notes |
|---|---|---|
| **CLI tool** | A `"bin"` field in `package.json` | Node.js CLI |
| | `main.go` + a `cobra`/`urfave/cli` dependency | Go CLI |
| | `[project.scripts]` in `pyproject.toml` or `entry_points` in `setup.py` | Python CLI |
| **React Native** | `"react-native"` dependency | iOS/Android app |
| | `metro.config.js` present | RN bundler signal |
| **Flutter** | `pubspec.yaml` present | iOS/Android/Desktop |
| **Go service/CLI** | `go.mod` + no web-framework dependency | Non-web if there is no frontend, even with an HTTP server |
| **Python service** | `pyproject.toml`/`requirements.txt` + no web-framework dependency | FastAPI/Django are backends — distinguish from a web frontend |

> **Electron is not a non-web type** — it is its own verdict, checked before this table (see
> `integration/SKILL.md` §2). See [`electron.md`](electron.md) for the full hybrid procedure.

---

## 2. human-in-the-loop Procedure

When classified as non-web, collect the following via `AskUserQuestion`.

### 2.1 Items to Collect

```
This project was detected as non-web (<type>).
No integration-test automation tool is enforced.

Please provide the following:

1. The core scenarios to verify
   e.g., "look up data after user login", "check the conversion result after a file upload"

2. The pass criteria for each scenario
   e.g., "response code 200 + an id field in the body", "the converted file is created in ./output/"

3. The test tool you are currently using (if any)
   e.g., "running a Postman collection with Newman", "none"

4. Automation priority
   e.g., "API endpoint contract tests first", "a manual checklist is enough"
```

### 2.2 Handling After Collection

Based on the collected scenarios, write a **manual verification checklist**:

```markdown
## Integration Verification Checklist — <date>

### Scenario 1: <scenario name>
- [ ] Preconditions: ...
- [ ] Execution steps: ...
- [ ] Pass criteria: ...
- [ ] Actual result: (manual entry)
- [ ] Verdict: PASS / FAIL

### Verdict Summary
| Scenario | Verdict |
|---|---|
| <Scenario 1> | PASS |
| <Scenario 2> | FAIL |

**Overall verdict**: FAIL (1 failure)
```

---

## 3. Reference OSS (not automatically enforced)

The tools below are free, commercially usable OSS you can leverage for non-web integration testing.
This skill does **not automatically install or run** the tools — it only provides guidance.

### 3.1 Newman (API contract testing)

Source: https://github.com/postmanlabs/newman (Apache-2.0)

A tool that runs Postman collections from the CLI. Well suited to REST API contract testing.

```bash
# Install
npm install -g newman

# Run a Postman collection
newman run collection.json -e environment.json --reporters cli,junit --reporter-junit-export results.xml
```

**Suitable scenarios**: REST API endpoint contract verification, CI pipeline integration.

### 3.2 Maestro (mobile UI testing)

Source: https://maestro.dev/ · https://github.com/mobile-dev-inc/maestro (Apache-2.0)

Define and run the UI flows of React Native/Flutter/iOS/Android apps in YAML.

```yaml
# example: login-flow.yaml
appId: com.example.myapp
---
- launchApp
- tapOn: "Email input"
- inputText: "test@example.com"
- tapOn: "Log in"
- assertVisible: "Home screen"
```

```bash
# Run
maestro test login-flow.yaml
```

**Suitable scenarios**: verifying core UI flows of React Native/Flutter apps.

### 3.3 Appium (cross-platform mobile automation)

Source: https://github.com/appium/appium (Apache-2.0)

Automates iOS/Android/Windows/macOS via the WebDriver protocol. It has a steep learning curve but
the broadest applicability.

```bash
# Install
npm install -g appium
appium driver install uiautomator2   # Android
appium driver install xcuitest       # iOS

# Start the server
appium
```

**Suitable scenarios**: mobile apps needing cross-platform integration, or cases requiring control of native elements.

---

## 4. Recommended Approach by Non-Web Type

| Type | Recommended approach | Reference tool |
|---|---|---|
| CLI tool | Test stdin/stdout and exit codes | `pytest`, Go `testing`, Jest |
| REST API service (no frontend) | Postman collection → run with Newman in CI | Newman (Apache-2.0) |
| React Native | Define flows in Maestro YAML | Maestro (Apache-2.0) |
| Flutter | `flutter test` integration tests + Maestro | Maestro (Apache-2.0) |
| Electron (renderer) | Playwright chromium channel | [`electron.md`](electron.md) |
| Electron (main process, IPC) | human-in-the-loop manual checklist | [`electron.md`](electron.md) |
| iOS/Android native | Appium WebDriver | Appium (Apache-2.0) |

---

## 5. SSOT URL Summary

| Item | URL | License |
|---|---|---|
| Newman | https://github.com/postmanlabs/newman | Apache-2.0 |
| Maestro | https://maestro.dev/ | Apache-2.0 |
| Maestro GitHub | https://github.com/mobile-dev-inc/maestro | Apache-2.0 |
| Appium | https://github.com/appium/appium | Apache-2.0 |
