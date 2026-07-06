# harness-tier

[English](README.md) · **한국어**

**작업의 위험도에 따라 AI 프로세스 강도를 자동으로 조절하는 Claude Code 플러그인.**

문서 한 줄 수정에는 가볍게, 핵심 비즈니스 로직 변경에는 무겁게 — 모든 작업에 똑같이
무거운 절차를 강요하지 않습니다. 여기에 팀 협업용 **Teams 알림**이 함께 들어 있습니다.

> 📖 각 스킬·설정의 자세한 사용법, 문제 해결, 갱신·제거는 **[USAGE.ko.md](USAGE.ko.md)** 에 있습니다.

## 핵심 생각

무거운 AI 파이프라인(설계→계획→구현→검증→리뷰)을 **모든 변경에 똑같이** 돌리면
문서 오타 하나 고치는 데도 과한 절차가 붙습니다. harness-tier 는 그 반대입니다:

> **절차의 무게를 위험도에 비례시킨다.**

이 한 문장이 세 가지 설계로 이어집니다.

1. **위험도 분류 → 등급별 절차** — `/flow` 가 작업을 받으면 먼저 **코드냐 아니냐**로
   위험도(Docs / Dev)를 나누고, 그 등급에 필요한 절차와 품질 게이트만 실행합니다.
   위험한 변경일수록 더 많은 검증을 통과해야 커밋됩니다.
2. **문서가 아니라 게이트로 강제** — "이렇게 하자"는 규율을 문서로만 두면 지켜지지
   않습니다. harness-tier 는 규율을 **커밋 훅**으로 강제합니다. `/flow` 분류를 거치지
   않은 커밋은 등급 마커가 없어 **차단(fail-closed)** 됩니다.
3. **한 번 만들면 이식되는 하네스** — 브랜치명·테스트 명령 같은 저장소별 값은 모두
   설정 파일로 빠져 있어, 새 저장소에는 `/flow-init` 한 번으로 그대로 옮겨집니다.
   게이트는 **프로젝트 언어와 무관**하게 동작합니다(Go/JS/Java/C++/C#/Rust 저장소도 동일).

## 장점

- **과하지도 부족하지도 않은 절차** — 오타 수정은 즉시, 로직 변경은 설계·리뷰·테스트를
  거쳐서. 등급이 알아서 결정합니다.
- **우회할 수 없는 규율** — 미분류 커밋을 커밋 시점에 차단해, "바빠서 건너뛰는" 것을
  구조적으로 막습니다.
- **저장소 간 이식성** — 거버넌스 설정을 파일로 분리해 새 저장소에 그대로 복제됩니다.
- **프로젝트 하네스 자동 생성** — `/harness-init` 이 프레임워크를 감지해 그에 맞는
  `CLAUDE.md`·규칙·기술 문서를 웹 리서치 + 코드 분석으로 만들어 줍니다.
- **팀 알림 내장** — 입력을 기다릴 때 또는 원하는 시점에 Microsoft Teams 채널로 알립니다.

## 요구 의존성

게이트가 **조용히 무력화되지 않고** 제대로 동작하려면 아래가 필요합니다. 대부분
`/flow-init` 이 점검하고 동의를 받아 설치하므로 미리 모두 갖출 필요는 없지만,
설치 전에 직접 준비해 두어도 됩니다.

| 항목 | 수준 | 없으면 |
|------|------|--------|
| `bash` + coreutils(`timeout`·`grep`·`sed`·`awk`) | 필수 | 게이트가 조용히 무력화됨(Windows 는 Git Bash) |
| **Python ≥ 3.8** + **PyYAML** | 필수 | 커밋이 **차단**됩니다(조용한 미강제 방지) |
| `pre-commit` | 권장 | lint·포맷·커밋 메시지 검사만 빠짐 |
| **`superpowers`** 플러그인 | Dev 작업에 필수 | Dev 등급에서 `/flow` 가 중단하고 설치를 안내 |

## 설치

### 1. 의존성부터 설치

**Python ≥ 3.8** — OS 패키지 관리자로 설치합니다(이미 있으면 건너뜀).

```bash
# Windows
winget install Python.Python.3.12
# macOS
brew install python@3.12
# Debian/Ubuntu
sudo apt install python3 python3-pip
```

**PyYAML + pre-commit** — 게이트 훅이 부르는 **그 `python3`** 에 들어가야 하므로
`python3 -m pip` 로 설치합니다(가상환경 전용 `uv add` 는 훅이 못 볼 수 있음).

```bash
python3 -m pip install pyyaml pre-commit
```

**`superpowers` 플러그인** — Dev 등급 작업의 구현 파이프라인이 이 플러그인을 씁니다.

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install superpowers@claude-plugins-official
```

### 2. 플러그인 설치

```
/plugin marketplace add foryouself83/harness-tier
/plugin install harness-tier@harness-tier
```

> 공개 저장소라 별도 인증 없이 설치·자동 업데이트가 됩니다.

### 3. `/harness-init` — 프로젝트 하네스 생성

프로젝트에 맞는 `CLAUDE.md`·규칙·기술 문서를 만듭니다. **아무것도 없는 새 프로젝트라면
여기서부터** 시작하세요 — 설명서(하네스)를 먼저 갖춘 뒤 게이트를 거는 것이 자연스럽습니다.
이미 `CLAUDE.md` 가 잘 갖춰진 기존 프로젝트라면 건너뛰어도 됩니다.

### 4. `/flow-init` — 거버넌스 배선

대화형 마법사가 설정 파일 생성, 커밋 게이트 등록·pre-commit 훅 점검, 자동 업데이트 등록,
Teams 연동을 자동으로 합니다(여러 번 실행해도 안전). 마지막으로:

```bash
pre-commit install --hook-type commit-msg --hook-type pre-push
```

이후 **`/flow <작업 설명>`** 으로 일상 작업을 시작합니다.

> 설치 후 호스트 저장소에 생기는 것은 모두 **`.claude/harness-tier/`** 한곳에 모입니다
> (설정·스크립트·게이트 증거). 자세한 구조는 [USAGE.ko.md](USAGE.ko.md) 를 참고하세요.

## 제공물

| 종류 | 항목 | 역할 |
|------|------|------|
| 스킬 | `/flow` | 위험도 분류 → 등급별 워크플로 실행 → 게이트 증거 기록 |
| 스킬 | `/flow-init` | 설치/갱신 마법사 (최초 설정 + 재실행 시 재동기화·재설정, 설정값 보존) |
| 스킬 | `/flow-uninstall` | 호스트에 설치된 harness-tier 배선 제거 |
| 스킬 | `/harness-init` | 프레임워크 감지 + 리서치·검증으로 하네스 생성 (`.md` 기본, 덮어쓰기 없음) |
| 스킬 | `doc-sync` | 코드 ↔ 문서 동기화 + 문서 집합 일관성 |
| 스킬 | `harness-insight` | 지정 기간 Claude Code 활동 집계 + 인사이트 리포트 |
| 스킬 | `playwright-scaffold` · `integration` · `performance` | E2E 스캐폴드 / 통합·성능 검증(비강제 수동 스킬) |
| 에이전트 | `harness-researcher` · `harness-code-analyzer` · `harness-critic` | 하네스 생성용 리서치 / 코드 분석 / 생성물 검증 |
| 룰 | `risk-tiers` | 위험도 분류 + 커밋 규율의 단일 기준 |
| 훅 | SessionStart · Notification · PreToolUse(commit) | 규칙 주입 · Teams 알림 · 커밋 게이트 |

## 갱신·제거

- **갱신** — 플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않습니다.
  `/flow-init` 을 다시 실행하면 재동기화됩니다(설정값·웹훅은 보존).
- **제거** — ⚠️ **`/plugin uninstall` 전에 반드시 `/flow-uninstall` 을 먼저 실행하세요.**
  정리 도구가 플러그인 안에 있어, 플러그인을 먼저 지우면 호스트에 남은 설정을 자동으로
  치울 수 없습니다.

> 갱신·제거의 자세한 절차와 수동 정리법은 [USAGE.ko.md](USAGE.ko.md) §9 에 있습니다.

## 라이선스

Apache License 2.0 — [LICENSE](LICENSE) 참고.
