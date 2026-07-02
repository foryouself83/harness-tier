# Teamer 자격증명 keyring 이전 + 스크립트 소유 리팩터

**날짜:** 2026-06-23
**상태:** 설계 승인 대기

## 1. 문제

Teamer 연동(task-import / task-sync)이 마스터 id/pw를 평문 `teamer_account.md`로
저장하고, 두 에이전트(teamer-api-searcher · teamer-item-updater)가 인증 시 **id/pw/token을
모델이 생성하는 명령어 문자열에 직접 끼워 넣는다**(`{"username":"<id>","password":"<password>"}`).
그 결과 매 실행마다 비밀이 모델 컨텍스트 → 대화 트랜스크립트 → 로그로 흘러간다.
`.gitignore`는 *저장소 유출* 한 가지만 막을 뿐, 이 컨텍스트 유입과 디스크 평문은 못 막는다.

Teamer는 PAT/API 토큰을 지원하지 않아 마스터 id/pw가 머신에서 무인 조회 가능해야 한다.
위험을 0으로 만들 수는 없으나(자동화 주체=OS 사용자 권한 프로세스는 결국 접근 가능),
**노출면**(평문 파일·모델 컨텍스트·트랜스크립트·로그)은 제거할 수 있다.

## 2. 목표 / 비목표

- **목표:** 비번/토큰이 LLM 컨텍스트·트랜스크립트·평문 파일에 **절대** 노출되지 않게 한다.
- **목표:** 자격증명 처리를 모델 → 독립 스크립트로 이전. 비밀은 OS 키체인(keyring)에만.
- **목표:** 최초 1회 setup 외 사용자 재입력 없음(세션·재부팅 무관 영구 유지).
- **비목표:** CI/헤드리스 지원 — **로컬 데스크톱 전용**(env-var fallback 없음).
- **비목표:** 토큰 캐시 — 매 호출 keyring 비번으로 자동 재로그인(YAGNI, 로컬이라 비용 무시).

## 3. 아키텍처

```
스킬(오케스트레이션·사용자판단·파일/브랜치)  ──호출(비밀 없는 인자)──▶  scripts/teamer_api.py
                                                                          │ keyring에서 id/pw 읽음
   ◀── 최소 JSON(item_no/title/content/status) ──                         ▼ 인증·GET·PUT (메모리 내)
                                                                       teamer.live API
```

- 새 컴포넌트 `scripts/teamer_api.py` — Python, **stdlib만**(HTTP=`urllib`) + 새 의존성 **`keyring`** 하나.
- **Node 의존성 제거**: urllib이 UTF-8 multipart를 명시 바이트 인코딩으로 안전 처리(Windows curl 깨짐은 curl 한정 문제).
- 비번/토큰은 스크립트 프로세스 **메모리에만** 존재. 토큰 캐시 파일 없음.
- 두 에이전트(teamer-api-searcher · teamer-item-updater)는 **삭제** — 하는 일이 100% 기계적
  API 오케스트레이션이고, 스크립트가 비밀 캡슐화 + 최소 출력(대용량 JSON 컨텍스트 격리)을
  모두 흡수한다. /flow는 에이전트를 직접 부르지 않으므로(스킬을 부름) 영향은 호출 3곳뿐.

## 4. 스크립트 인터페이스 (I/O 계약)

| 서브커맨드 | 인자(비밀 없음) | 출력(최소 JSON) |
|---|---|---|
| `setup` | (없음, 대화형) | 성공/실패 메시지만 |
| `search` | `--project-no --workitem-no --text` | `[{item_no, item_id, item_title, item_content, status_name}]` |
| `update` | `--project-no --workitem-no --item-no --searchtext --content-file [--col-override colXX=FILE ...] [--target-status-name --workflow-no]` | `{item_id, item_title, item_workflow_status_no, mode}` |

- **필드 보존을 스크립트 내부에서**: `update`가 자체 GET → non-null colXX 전부 보존 →
  `item_content`는 기존+신규 **append** → multipart PUT. (지금 LLM이 하던 깨지기 쉬운 로직이
  결정적 코드로 이동 — 보안뿐 아니라 정확성 개선.)
- **status 해석**(name→no)도 `update` 내부에서 workflowAction 조회. 스킬은 *판단*(어떤
  status로 갈지), 스크립트는 *해석/적용*.
- 큰 HTML 본문은 명령줄이 아니라 `--content-file`로 전달(비밀 아님, 안전). col_overrides도 파일로.
- Auth 헤더: `Authorization: Bearer {token}` + `Cookie: Admin-Token={token}; language=ko` 둘 다.

## 5. 자격증명 수명주기

- **`setup`(터미널 전용, 대화형)**: 호스트 `.claude/vway-kit/config/teamer_account.md`가 있으면
  → 값을 keyring으로 이전 후 **파일 삭제**. 없으면 → `getpass`로 id/비번 입력받아 저장.
  **AskUserQuestion으로 비번 받지 않음**(모델 컨텍스트 오염 방지).
- **keyring 스키마**: service=`vway-kit-teamer`, 엔트리 `id` / `password` 두 개. OS 키체인 암호화 저장.
- **search/update**: 매 실행 keyring에서 읽음. **비어있으면** "터미널에서 `python teamer_api.py
  setup` 실행" 안내 후 비차단 종료(지어내지 않음). id/pw/token을 **절대 출력하지 않음**(에러도 새니타이즈).
- **keyring 미설치**: 명확한 설치 안내(`python3 -m pip install keyring`)와 함께 종료. bare python
  환경에 설치(uv venv 아님 — PyYAML과 동일 이슈).
- **영구성**: keyring=OS 로그인 사용자에 묶임 → 세션 종료·재부팅·다른 프로젝트 무관 유지.
  재입력 필요 시점: 비번 rotate / 다른 OS 계정 / 다른 머신뿐.

## 6. 스킬 변경 (에이전트 제거 → 스크립트 직접 호출)

**삭제:** `agents/teamer-api-searcher.md`, `agents/teamer-item-updater.md`

**`skills/task-import/SKILL.md`:**
- 1단계(평문 Read + id/pw 추출) 제거 → keyring. 미설정 시 setup 안내 후 중단.
- 2단계: searcher 호출 → `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" search ...`. id/pw 인자 라인 전부 삭제.
- 3·4·5단계(추출·git-branch-manager·task 파일 쓰기) 유지.
- `allowed-tools`에서 `Agent` 제거(`Bash` 유지).

**`skills/task-sync/SKILL.md`:**
- 1단계(credential Read) 제거 → keyring.
- 6단계: searcher → `teamer_api.py search`. 다중 결과면 사용자 선택(스킬), `item_no`/`status_name`
  추출. "non-null colXX 보존" 책임 문구 제거(스크립트가 함).
- 8단계: updater → `teamer_api.py update`. 생성 HTML은 temp 파일 → `--content-file`,
  col_overrides는 `--col-override colXX=FILE`. append/보존/status해석은 스크립트 내부.
- `allowed-tools`에서 `Agent` 제거.

## 7. CLAUDE.md · 문서 · 의존성

- **CLAUDE.md Invariant #6 재작성**: 자격증명은 keyring에서 스크립트가 읽음(평문파일·모델컨텍스트
  금지). PUT은 multipart/form-data·UTF-8 **Python urllib**(Node→Python). GET non-null colXX
  보존·status name→no 해석은 스크립트 내부. **+ 새 불변식: 비밀은 모델 컨텍스트/트랜스크립트/평문 노출 금지.**
- **CLAUDE.md Folder structure**: `agents/`에서 두 teamer 항목 제거, `scripts/`에 `teamer_api.py`
  추가, config 설명의 `teamer_account.md`를 "setup 마이그레이션용 임시(이전 후 삭제)"로 갱신.
- **`scripts/check-deps.sh`**: `keyring` 점검 항목 추가(teamer 연동용·권장, flow-init 비차단 —
  teamer는 코어 게이트 아님). 안내: `python3 -m pip install keyring`.
- **`scripts/flow_init_setup.py`**: COPY_MAP에서 `teamer_account.md` 시딩 제거. `.gitignore` 라인은 방어적 유지.
- **README.md**: 에이전트 표에서 두 teamer 항목 제거 + **"Teamer 인증 설정" 짧은 절 추가**
  (keyring 기반·최초 1회 setup·평문 미저장 핵심만 간략히). 준비물(L57)의 `teamer_account.md`
  안내를 setup 흐름으로 갱신.
- **USAGE.md**: 에이전트 표 항목 제거. §7 Teamer 연동의 "계정 — teamer_account.md" 절을 keyring
  setup으로 갱신(1회 실행 + 재입력 불필요 한두 줄). 준비물(L46) 갱신.
- 플러그인 루트 `teamer_account.md`(살균됨): 제거.

## 8. 테스트 (`tests/test_teamer_api.py`, 순수함수 TDD 패턴)

네트워크/keyring 없이 순수 로직 검증:
- `merge_preserve_fields(get_response)` — non-null colXX 보존 + 누락→null 규칙
- `append_item_content(existing, new)` — null/빈값 처리 포함 append
- `build_multipart(fields, boundary)` — UTF-8 바이트·boundary·CRLF(한글 포함)
- `resolve_status_no(actions, target_name)` — name→no 매핑, 미매치 에러
- `redact(text)` — 로그/에러에서 id/pw/token 마스킹
- keyring·HTTP는 얇은 레이어로 격리해 mock. 실네트워크 테스트 없음.

**Windows 인코딩**(Invariant #2): `PYTHONUTF8`/force-utf8 io·`encoding="utf-8"` 방어,
JSON 출력은 `ensure_ascii=False` + utf-8.

## 9. 잔여 위험 (명시)

- 무인 자동화 특성상 OS 사용자 권한 프로세스는 keyring 비번을 조회할 수 있다 — PAT/OAuth
  없이는 암호학적으로 못 막는다. 신뢰 경계는 LLM이 아니라 **로컬 실행 환경(OS 계정)**.
- 본 설계가 제거하는 것: 평문 파일 / 모델 컨텍스트·트랜스크립트·로그 노출 / 저장소 유출.
- 별도 조치(사용자): 이미 노출된 현재 비번 **교체(rotate)**.
