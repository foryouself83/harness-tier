# harness-tier

[English](README.md) · **한국어**

**작업의 위험도에 따라 AI 프로세스 강도를 조절하는 Claude Code 플러그인.**

문서 한 줄 수정에는 가볍게, 핵심 비즈니스 로직 변경에는 무겁게. 팀 협업용 **Teams 알림** 내장.

> 📖 각 스킬·설정의 사용법, 문제 해결, 갱신·제거는 **[USAGE.ko.md](USAGE.ko.md)** 참고.

## 핵심 생각

무거운 AI 파이프라인(설계→계획→구현→검증→리뷰)을 **모든 변경에 똑같이** 돌리면 문서 오타
하나에도 과한 절차가 붙음. harness-tier 는 그 반대:

> **절차의 무게를 위험도에 비례시킬 것.**

여기서 세 가지 설계가 나옴.

1. **위험도 분류 → 등급별 절차** — `/flow` 가 작업을 **코드냐 아니냐**로 나누고(Docs / Dev),
   그 등급에 필요한 절차와 품질 게이트만 실행. 위험할수록 커밋 전에 통과할 검증이 많아짐.
2. **문서가 아니라 게이트로 강제** — 문서로만 둔 규율은 지켜지지 않음. harness-tier 는 **커밋
   훅**으로 강제하며, `/flow` 분류를 거치지 않은 커밋은 등급 마커가 없어 **차단(fail-closed)**.
3. **한 번 만들면 이식되는 하네스** — 브랜치명·테스트 명령 같은 저장소별 값은 모두 설정 파일에
   있어 새 저장소에는 `/flow-init` 한 번으로 옮겨짐. 게이트는 **프로젝트 언어와 무관**
   (Go/JS/Java/C++/C#/Rust 저장소도 동일).

## 왜 harness-tier 인가

**품질이 소리 없이 나빠지지 않음.** AI 는 누가 규율을 잡는 속도보다 빠르게 코드를 씀 — 테스트는
건너뛰고, 문서는 어긋나고, "빠른 수정"이 리뷰 없이 나감. harness-tier 는 각 변경에 필요한 검증을
위험도 등급에 묶어 **커밋 시점에 강제**하므로, 위험한 변경은 그 검증 없이 반영될 수 없음.

대부분의 Claude Code 플러그인은 한 갈래만 맡음. harness-tier 는 다른 축 — 어떤 변경에 절차가
*얼마나* 필요한지를 결정하고 강제함:

| 관점 | 방법론 플러그인 (예: [`superpowers`](https://github.com/obra/superpowers)) | 가드레일·보안 플러그인 | **harness-tier** |
|------|--------------------------------------------------------------------------|----------------------|------------------|
| 최적화 대상 | *어떻게* 잘 만들지 — TDD·디버깅·스펙 기반 계획 | 위험 행동 차단·취약점 스캔 | 그 변경에 절차가 *얼마나* 필요한지 |
| 작업마다 | 매번 같은 격식 | 매번 같은 검사 | **위험도 등급에 맞춰 조절** |
| 강제 방식 | 권고 | 특정 행동 차단 | **커밋 게이트 — 미분류 커밋은 차단(fail-closed)** |

이들과 경쟁하지 않음 — Dev 등급은 **`superpowers` 위에서 돌고**, 가드레일 플러그인과도 나란히
씀. 그 방법론 계층 위에 그들이 다루지 않는 거버넌스를 더함: **하네스 생성 → 알맞은 절차 강제 →
문서와 CI 동기화 → 실제 작업 방식으로부터 진화**.

| 역량 | 무엇을 얻나 |
|------|-------------|
| **위험도 등급 분류 + 강제** | 오타 수정은 즉시 커밋, 로직 변경은 설계·리뷰·테스트를 먼저 통과. `/flow` 분류를 건너뛴 커밋은 커밋 훅이 차단하고, **`git worktree` 에서 커밋해도 게이트가 그대로 적용**(Dev 파이프라인이 자주 쓰는 방식). |
| **프로젝트 하네스 스캐폴딩** | `/harness-init` 이 스택을 인식해(**언어 12종과 프레임워크** — [지원 목록](USAGE.ko.md#자동-감지-언어와-프레임워크)) 맞춤 `CLAUDE.md` **와 자동 로드되는 `.claude/rules/`**(`paths` 로 매칭 파일에만 높은 우선순위로 로드), 주제별 기술 문서를 실시간 웹 리서치·실제 코드 분석으로 생성. 기본은 `.md` 파일만 쓰고 기존 파일은 덮어쓰지 않으며, **항목별 동의**로 폴더 구조·CI·보안 도구까지 만듦. |
| **한 파일로 끝내는 품질 게이트** | lint · 정적 분석 · import 린팅 · 테스트 · 보안 스캔 · API 계약 테스트를 모듈별로 하나의 `flow-config.yaml` 에 선언 — **모듈·브랜치·CI 잡을 자유롭게 확장**. **언어 무관**으로 설정한 명령을 실행할 뿐이며, 새 저장소는 `/flow-init` 한 번으로 전체 구성을 물려받고 활성 등급에 필요한 것만 실행. |
| **파일을 빠뜨릴 수 없는 리뷰** | `review` 게이트는 변경 파일 목록을 **`git` 에서 직접** 가져와 전부 리뷰하고 그 개수를 보고서에 명시하므로, 큰 변경분에서 일부만 보고 나머지를 넘기는 일이 없음. 여기에 **변경된 public 심볼의 호출자**까지 language server(없으면 `grep`)로 확인 — 회귀가 실제로 터지는 자리이고 diff 만으로는 드러나지 않음. 판정은 독립 리뷰 에이전트가 팀의 `review_checklist` 기준으로 수행. |
| **살아 있는 문서 SSOT** | `doc-sync` 가 코드와 문서를 함께 diff — 코드 변경은 관련 마크다운으로 전파되고 문서 변경은 문서 집합 전체에서 조율되며, `doc_style_check.py` 가 그 재작성이 heading·코드 블록·URL·인라인 코드를 하나도 잃지 않았음을 증명. |
| **스스로 작성되는 CI** | `/flow-init` 이 설정으로부터 GitHub Actions 를 렌더링 — 유닛 테스트 안전망, API 계약 테스트, Conventional Commits 로 버전을 올리고 태깅하는 시맨틱 릴리스, wiki·문체 검증, 브랜치명·entropy 검사, 모든 잡에 timeout 상한. |
| **릴리스 위에 얹는 배포** | `/harness-deployments` 가 산출물 없는 릴리스에 발행을 더함 — 스택 감지 → 무엇을 어디에 배포할지 질문 → CI 렌더. `release.yml` 이 **같은 런**에서 호출하는 오케스트레이터(크로스-워크플로우 트리거·PAT 불필요)가 타깃별 컴포넌트(PyPI · npm · Maven Central/Gradle · NuGet · crates.io · GHCR · Docker Hub, 그리고 저작된 앱 배포)로 분기하며 타깃별 최소권한을 적용. |
| **당신에게서 배우는 하네스** | `harness-insight` 가 Claude Code 활동을 집계해 반복해서 내리는 지시를 **하네스 후보**로 드러내고, 낡은 메모리를 정리. |
| **팀 알림 내장** | 워크플로가 입력을 기다릴 때, 또는 원하는 체크포인트에서 Microsoft Teams 채널로 알림. |

## 요구 의존성

게이트가 **조용히 무력화되지 않으려면** 아래가 필요함. 대부분 `/flow-init` 이 점검하고 동의를
받아 설치함.

| 항목 | 수준 | 없으면 |
|------|------|--------|
| `bash` + coreutils(`timeout`·`grep`·`sed`·`awk`) | 필수 | 게이트가 조용히 무력화됨(Windows 는 Git Bash) |
| **Python ≥ 3.8** + **PyYAML** | 필수 | 커밋이 **차단**됨(조용한 미강제 방지) |
| `pre-commit` | 권장 | 커밋 메시지 검사(gitlint)·push 알림·언어무관 기본 파일 점검(공백·개행·yaml 검증 등)만 빠짐 — 모듈 lint/정적/테스트는 flow 게이트가 계속 수행 |
| **`superpowers`** 플러그인 | Dev 작업에 필수 | Dev 등급에서 `/flow` 가 중단하고 설치를 안내 |

## 설치

### 1. 의존성부터 설치

**Python ≥ 3.8** — OS 패키지 관리자로 설치(이미 있으면 건너뜀).

```bash
# Windows
winget install Python.Python.3.12
# macOS
brew install python@3.12
# Debian/Ubuntu
sudo apt install python3 python3-pip
```

**PyYAML + pre-commit** — 게이트 훅이 부르는 **그 `python3`** 에 들어가야 하므로
`python3 -m pip` 로 설치(가상환경 전용 `uv add` 는 훅이 못 볼 수 있음).

```bash
python3 -m pip install pyyaml pre-commit
```

**[`superpowers`](https://github.com/obra/superpowers) 플러그인** — Dev 등급 작업의 구현
파이프라인이 이 플러그인을 씀.

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install superpowers@claude-plugins-official
```

### 2. 플러그인 설치

```
/plugin marketplace add foryouself83/harness-tier
/plugin install harness-tier@harness-tier
```

> 공개 저장소라 별도 인증 없이 설치·자동 업데이트 가능.

### 3. `/harness-init` — 프로젝트 하네스 생성

프로젝트에 맞는 `CLAUDE.md`·규칙·기술 문서를 생성. **아무것도 없는 새 프로젝트라면 여기서부터**
— 설명서(하네스)를 먼저 갖춘 뒤 게이트를 거는 순서. 이미 `CLAUDE.md` 가 잘 갖춰졌으면
건너뛰어도 됨.

### 4. `/flow-init` — 거버넌스 배선

대화형 마법사가 설정 파일 생성, 커밋 게이트 등록·pre-commit 훅 점검, 자동 업데이트 등록, Teams
연동을 처리(여러 번 실행해도 안전). 마지막으로:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

이후 **`/flow <작업 설명>`** 으로 일상 작업 시작.

> 설치 후 호스트 저장소에 생기는 것은 모두 **`.claude/harness-tier/`** 한곳에 모임
> (설정·스크립트·게이트 증거). 자세한 구조는 [USAGE.ko.md](USAGE.ko.md) 참고.

## 제공물

| 종류 | 항목 | 역할 |
|------|------|------|
| 스킬 | `/flow` | 위험도 분류 → 등급별 워크플로 실행 → 게이트 증거 기록 |
| 스킬 | `/flow-init` | 설치/갱신 마법사 (최초 설정 + 재실행 시 재동기화·재설정, 설정값 보존) |
| 스킬 | `/flow-uninstall` | 호스트에 설치된 harness-tier 배선 제거 |
| 스킬 | `/harness-init` | 프레임워크 감지 + 리서치·검증으로 하네스 생성 (`.md` 기본, 덮어쓰기 없음) |
| 스킬 | `/wiki-init` | 문서를 지식 그래프로 — 임베딩 없이 front matter 기반, 설치 마법사 |
| 스킬 | `commit` | 커밋 하나를 작성·발행 — type 선택·50/72·스테이징. `/flow` 가 모든 커밋 단계에서 호출 |
| 스킬 | `doc-sync` | 코드 ↔ 문서 동기화 + 문서 집합 일관성 + 무손실 재작성 검증 |
| 스킬 | `harness-insight` | 지정 기간 Claude Code 활동 집계 + 인사이트 리포트 |
| 스킬 | `/harness-deployments` | 릴리스 워크플로 위에 배포(레지스트리 발행 / 컨테이너 이미지 / 앱 배포) 계층 추가 — 감지 → 질문 → 배포 CI 렌더(옵트인, `/flow-init` 이후) |
| 스킬 | `playwright-scaffold` · `integration` · `performance` | E2E 스캐폴드 / 통합·성능 검증(비강제 수동 스킬) |
| 에이전트 | `harness-researcher` · `harness-code-analyzer` · `harness-critic` | 하네스 생성용 리서치 / 코드 분석 / 생성물 검증 |
| 룰 | `risk-tiers` | 위험도 분류 + 커밋 규율의 단일 기준 |
| 룰 | `doc-style` | 문서·주석·docstring 문체 규율의 단일 기준 |
| 훅 | SessionStart · Notification · PreToolUse(commit·merge) · PostToolUse(편집) | 규칙 주입 + 구버전 로드 경고 · Teams 알림 · 커밋 게이트 + 머지 전략 게이트 · 편집으로 낡은 review/doc-sync 증거 무효화 |

> **릴리스 CI 토큰** — `/flow-init` 이 렌더링하는 릴리스 워크플로는 기본 `GITHUB_TOKEN` 으로 바로
> 돎(Actions 쓰기 권한만 부여). `RELEASE_TOKEN` 시크릿은 옵트인 확장. 자세한 내용은
> [USAGE.ko.md](USAGE.ko.md) 의 "릴리스 토큰 쓰기 권한" 절 참고.

## 갱신·제거

- **갱신** — 플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않음.
  `/flow-init` 을 다시 실행하면 재동기화됨(설정값·웹훅은 보존).
- **제거** — ⚠️ **`/plugin uninstall` 전에 반드시 `/flow-uninstall` 을 먼저 실행할 것.** 정리
  도구가 플러그인 안에 있어, 플러그인을 먼저 지우면 호스트에 남은 설정을 자동으로 치울 수 없음.

> 갱신·제거의 자세한 절차와 수동 정리법은 [USAGE.ko.md](USAGE.ko.md) §7 참고.

## 라이선스

Apache License 2.0 — [LICENSE](LICENSE) 참고.
