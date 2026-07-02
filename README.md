# vway-kit

작업의 **위험도에 따라 AI 프로세스 강도를 자동으로 조절**해 주는 Claude Code 플러그인입니다.
문서 한 줄 수정에는 가볍게, 핵심 비즈니스 로직에는 무겁게 — 모든 작업에 똑같이 무거운
절차를 강요하지 않습니다. 여기에 **Teamer.live 연동**(작업 가져오기/결과 동기화)과
**Teams 알림**이 함께 들어 있습니다.

한 번 만들어 두면 새 저장소에는 `/vdev-init` 한 번으로 그대로 옮겨집니다 — 브랜치명·테스트
명령·Teamer 번호 같은 저장소별 값은 모두 설정 파일로 빠져 있습니다.

> 📖 단계별 사용법·설정·문제 해결은 **[USAGE.md](USAGE.md)** 에 있습니다.

## 무엇을 해 주나

- **`/vdev`** — 작업을 받으면 위험도(Docs/Dev)를 먼저 분류하고, 그 등급에 맞는 절차와
  품질 게이트만 실행합니다. 등급이 높을수록 더 많은 검증을 통과해야 커밋됩니다.
- **`/harness-init`** — 프로젝트의 프레임워크를 감지해 그에 맞는 `CLAUDE.md`·규칙·기술 문서를
  자동 생성합니다(웹 리서치 + 코드 분석 기반).
- **`/task-import` · `/task-sync`** — Teamer 작업을 가져와 브랜치/문서를 만들고, 끝나면 결과를
  Teamer에 다시 올립니다.
- **Teams 알림** — 입력을 기다릴 때, 또는 원하는 시점에 Teams 채널로 알려 줍니다.

## 요구사항

게이트가 동작하려면 아래가 필요합니다(프로젝트 언어와 무관 — Go/JS/Java 저장소도 동일).
대부분 `/vdev-init`이 점검하고 동의를 받아 설치하므로, 미리 모두 갖출 필요는 없습니다.

| 항목 | 수준 | 없으면 |
|------|------|--------|
| `bash` + coreutils(`timeout`·`grep`·`sed`·`awk`) | 필수 | 게이트가 조용히 무력화됨(점검기 자신이 bash라 부재를 감지 못 함 → 직접 확인 필요) |
| `python3` ≥ 3.8 + `PyYAML` | 필수 | 커밋이 **차단**됩니다(설치를 강제하려는 의도). `python3 -m pip install pyyaml` |
| `pre-commit` | 권장 | lint·포맷·커밋 메시지 검사만 빠짐 |
| `keyring` | Teamer 연동 시 필요 | `/task-import`·`/task-sync`가 자격증명을 못 읽어 동작 안 함 |
| `superpowers` 플러그인 | Dev 작업에 필수 | Dev 등급에서 `/vdev`가 중단하고 설치를 안내 |

> 미리 점검만 하려면: `bash scripts/check-deps.sh` (확인·안내만, 설치는 안 함).

## 설치 및 시작

**1. 저장소 접근 준비 (SSH) — 비공개 저장소**

vway-kit은 비공개 저장소라, 플러그인을 받기 전에 먼저 이 저장소에 SSH로 접근할 수
있어야 합니다. **조직 저장소이므로** 먼저 조직 관리자에게 **멤버 초대 + 저장소 Read
권한**을 요청하세요(권한이 없으면 키를 등록해도 접근이 거부됩니다). 그다음 새 PC라면
순서대로:

1. SSH 키가 없으면 생성 — `ssh-keygen -t ed25519 -C "you@example.com"`
2. 공개키(`~/.ssh/id_ed25519.pub`)를 GitHub에 등록 — Settings → SSH and GPG keys → New SSH key
3. 호스트 키 등록 + 접근 확인 — `ssh -T git@github.com` 실행. 처음이면 fingerprint
   (`SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`)를 확인하고 `yes`.
   `Hi <아이디>! You've successfully authenticated, ...` 가 나오면 정상입니다.

> ⚠️ 이 단계를 건너뛰면 `marketplace add` 가 `Host key verification failed`(known_hosts
> 미등록) 또는 `Permission denied`(키 미등록)로 실패합니다. Claude Code의 `add` 는
> 비대화형이라 호스트 키 확인 프롬프트를 띄우지 못하므로, 위 `ssh -T` 로 **미리** 등록해야 합니다.

**2. 플러그인 추가**

```
/plugin marketplace add git@github.com:Developments-3/vway-kit.git
/plugin install vway-kit@vway
```

> `Developments-3/vway-kit` 축약형도 되지만, SSH URL을 쓰면 방금 준비한 SSH 키를 확실히
> 탑니다. 비공개 저장소의 **자동 업데이트**까지 받으려면 추가로 토큰 설정이 필요합니다
> (SSH와 별개 — 아래 "자동 업데이트 설정").

**3. `/harness-init` — 프로젝트 하네스 생성**

프로젝트에 맞는 `CLAUDE.md`·규칙·기술 문서를 만듭니다. **아무것도 없는 새 프로젝트라면
여기서부터 시작하세요** — 프로젝트 설명서(하네스)를 먼저 갖춘 뒤 게이트를 거는 것이
자연스럽습니다. (이미 `CLAUDE.md`가 잘 갖춰진 기존 프로젝트라면 건너뛰어도 됩니다.)

**4. 준비물 — Teamer·Teams를 쓸 경우 (`/vdev-init` 전)**

Teams 웹훅 URL은 이 시점엔 아직 `config/` 폴더가 없으니 **프로젝트 루트**에 두면 되고,
다음 `/vdev-init`이 `.claude/vway-kit/config/`로 옮겨 줍니다. Teamer 자격증명은 루트
파일이 아니라 아래 keyring 절차로 설정한다. 형식·등록법은 [USAGE](USAGE.md) §2·§7·§8.

- **Teamer** — 최초 1회 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 실행(getpass). 자격증명은 OS 키체인(keyring)에 저장되며 평문 파일로 두지 않는다. 한 번 설정하면 세션·재부팅과 무관하게 재입력 불필요.
- **Teams** — 개인 채널·브랜치 채널 웹훅 URL

### Teamer 인증 설정

Teamer 연동(`/task-import`·`/task-sync`)은 OS 키체인(keyring)에 저장된 자격증명을 사용한다.
평문 파일이나 대화에 비밀번호를 두지 않는다.

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup
```

- 기존 `teamer_account.md` 가 있으면 자동으로 keyring 으로 옮긴 뒤 그 평문 파일을 삭제한다.
- 없으면 `getpass` 로 id/비밀번호를 입력받는다(화면에 표시되지 않음).
- 최초 1회만 실행한다. 비밀번호 교체 시에만 재실행한다. `keyring` 미설치 시 `python3 -m pip install keyring`.

**5. `/vdev-init` — 거버넌스 배선**

대화형 마법사가 설정 파일 생성, 커밋 게이트 등록·pre-commit 훅 점검, 자동 업데이트 등록(아래
"자동 업데이트 설정" 참고), Teams/Teamer 연동, 루트 준비물의 `config/` 이전을 자동으로 합니다
(여러 번 실행해도 안전).

**6. 마무리**

- `uv run pre-commit install --hook-type commit-msg --hook-type pre-push`
- `pre-commit-hooks.example.yaml`의 언어별 검사 도구(ruff/bandit 등)를 팀 스택에 맞게 교체

이후 `/vdev <작업 설명 또는 Teamer 작업 번호>`로 일상 작업을 시작합니다.

> 설치 후 호스트 저장소에 생기는 것은 모두 **`.claude/vway-kit/`** 한곳에 모입니다
> (설정·스크립트·증거). 자세한 구조와 의미는 [USAGE.md](USAGE.md)를 참고하세요.

## 자동 업데이트 설정 (비공개 저장소)

vway-kit은 비공개 저장소라, **새 버전이 나와도 자동으로 받으려면 GitHub 인증을 한 번
설정**해야 합니다. 설정하지 않으면 자동 갱신이 (에러 없이) 조용히 건너뛰어집니다.
공개 저장소를 쓴다면 이 절은 건너뛰어도 됩니다.

아래를 순서대로 한 번만 해 두면 됩니다.

**1) GitHub 토큰(PAT) 발급**

> **조직 저장소라면 먼저** 조직 관리자에게 **조직 멤버 초대와 이 저장소의 Read 권한**을
> 요청하세요. 초대를 받아야 아래 발급 화면의 **Repository access** 목록에 이 저장소가
> 나타납니다(권한이 없으면 토큰을 만들어도 접근이 거부됩니다).

GitHub → Settings → Developer settings → **Fine-grained tokens** → **Generate new token**.
발급 화면에서 **순서대로** 설정한 뒤 생성합니다(권한 설정이 먼저, 그다음 생성):

1. **Repository access** → *Only select repositories* → 이 저장소 선택
2. **Permissions** → Repository permissions → **Contents: Read-only** (이 권한만 — 최소 권한 원칙)
3. **Generate token** 으로 생성하고 토큰 문자열을 복사

> **조직이 "Require administrator approval"을 켠 경우**, 발급한 토큰은 승인 전까지 대기
> 상태라 자동 갱신이 (에러 없이) 안 됩니다. 조직 관리자가 **조직 → Settings → Personal
> access tokens → Pending requests** 에서 승인해야 동작합니다.

**2) 토큰을 환경변수로 등록**

발급한 토큰을 `GITHUB_TOKEN`으로 설정합니다(셸 프로필 등 영구 위치에).

```bash
export GITHUB_TOKEN=github_pat_xxxxxxxx
```

**3) git이 토큰을 쓰도록 자격증명 헬퍼 등록**

git은 `GITHUB_TOKEN`을 **직접 읽지 않습니다.** 그래서 토큰만 설정하면 자동 갱신이
"비밀번호 없음"으로 실패합니다. 아래를 한 번 실행하면 git이 그 토큰을 쓰게 됩니다.

```bash
git config --global credential.https://github.com.helper ""
git config --global --add credential.https://github.com.helper \
  '!f() { test "$1" = get && echo username=x-access-token && echo "password=$GITHUB_TOKEN"; }; f'
```

**4) (해당될 때만) SSH 치환 예외 처리**

평소 `git@github.com`(SSH)으로 받도록 전역 설정(`insteadOf`)을 쓰고 있다면, 그게 토큰
(HTTPS)을 무력화합니다. **이 저장소만** HTTPS로 예외 처리하세요(다른 저장소의 SSH 설정은
그대로 유지됩니다).

```bash
git config --global url."https://github.com/Developments-3/vway-kit".insteadOf "https://github.com/Developments-3/vway-kit"
```

**5) 호스트를 완전히 재시작**

토큰은 프로그램이 **켜질 때** 읽힙니다. VS Code 등은 **모든 창을 닫고** 다시 여세요
(창 하나만 새로고침하면 옛 환경이 그대로 남습니다).

**제대로 됐는지 확인**

아래가 정상 출력(`exit 0`)이면 자동 갱신이 동작합니다.

```bash
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND=false git ls-remote https://github.com/Developments-3/vway-kit.git HEAD
```

실패하면 거의 항상 **3)** 헬퍼 누락 또는 **4)** SSH 치환 충돌입니다. "수동 갱신은 되는데
자동은 안 되는" 경우도 마찬가지입니다 — 수동(`/plugin marketplace update vway`)은 대화형이라
우회되지만 백그라운드 자동 갱신은 안 되기 때문입니다. 원리·정밀 진단은
[docs/plugins/marketplace-auto-update.md](docs/plugins/marketplace-auto-update.md)를 참고하세요.

## 제공물

| 종류 | 항목 | 역할 |
|------|------|------|
| 커맨드 | `/vdev` | 위험도 분류 → 등급별 워크플로 실행 → 게이트 증거 기록 |
| 커맨드 | `/vdev-init` | 설치/갱신 마법사 — 최초 설정 + 재실행 시 재동기화·슬롯 보충·재설정 (설정값 보존) |
| 커맨드 | `/vdev-uninstall` | 호스트에 설치된 vway-kit 배선 제거 |
| 커맨드 | `/harness-init` | 프레임워크 감지 + 리서치·검증으로 하네스 생성 (`.md` 기본, 덮어쓰기 없음) |
| 커맨드 | `/task-import` · `/task-sync` | Teamer 작업 가져오기 / 결과 동기화 |
| 에이전트 | `harness-researcher` · `harness-code-analyzer` · `harness-critic` | 하네스 생성용 리서치 / 코드 분석 / 생성물 검증 |
| 룰 | `risk-tiers` | 위험도 분류 + 커밋 규율의 단일 기준 |
| 스킬 | `doc-sync` | 코드 ↔ 문서 동기화 + 문서 집합 일관성 |
| 스킬 | `harness-insight` | 지정 기간 Claude Code 활동 집계 + 인사이트 리포트 + 메모리 정리 |
| 스킬 | `playwright-scaffold` · `integration` · `performance` | E2E 스캐폴드 / 통합·성능 검증(비강제 수동 스킬) |
| 훅 | SessionStart · Notification · PreToolUse(commit) | 규칙 주입 · Teams 알림 · 커밋 게이트 |

## 갱신·제거

- **갱신** — 플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않습니다.
  `/vdev-init`을 다시 실행하면 재동기화됩니다(설정값·계정·웹훅은 보존). 예전
  `/vdev-upgrade`는 `/vdev-init`에 통합되었습니다.
- **제거** — ⚠️ **`/plugin uninstall` 전에 반드시 `/vdev-uninstall`을 먼저 실행하세요.**
  정리 도구가 플러그인 안에 있어, 플러그인을 먼저 지우면 호스트에 남은 설정을 자동으로
  치울 수 없습니다(수동 정리는 [USAGE.md](USAGE.md) 참고 — 핵심은 `rm -rf .claude/vway-kit/` +
  등록 4곳 제거).

## 라이선스

VWAY Corporation Proprietary (사내 전용).
