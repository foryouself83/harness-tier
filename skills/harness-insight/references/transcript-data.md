# 트랜스크립트 데이터 계약 (harness_insight.py 의존 SSOT)

`scripts/harness_insight.py` 가 프롬프트·활동을 추출하는 **데이터 출처와 스키마**.
이 형식은 Claude Code 가 소유하며(외부 패키지 아님 — 표준 라이브러리만으로 파싱),
포맷이 바뀌면 추출이 깨질 수 있는 지점을 여기에 박제한다. 형식은 모델 지식이 아니라
**실제 `*.jsonl` 을 SSOT 로** 확인해 갱신한다.

---

## 1. 위치

```
~/.claude/projects/<slug>/<sessionId>.jsonl
```

- `<slug>` = cwd 절대경로의 비영숫자 문자를 `-` 로 치환한 값
  (`re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())`).
- **git worktree** 는 다른 파일 경로 → 다른 `<slug>` 디렉터리에 저장된다. worktree 슬러그는
  메인 저장소 슬러그를 **접두사로 공유**하므로 `<slug>*` 접두 glob 으로 한데 모은다
  (`project_dirs_from_cwd`). 부작용: `myapp-v2` 처럼 슬러그가 접두사로 겹치는 *형제 프로젝트*도
  매칭될 수 있어, `main` 이 수집된 디렉터리를 출력해 가시화한다.
- 외부 유출 없음 — 모든 처리는 로컬 파일 읽기뿐.

## 2. 레코드 구조 (JSON Lines — 한 줄 = 한 레코드)

각 줄은 독립 JSON 객체. 손상 줄은 건너뛴다(`json.JSONDecodeError` 무시). 손상 바이트는
`errors="replace"` 로 관대 디코딩해 한 줄 오류가 주간 수집 전체를 중단시키지 않게 한다.

공통 상위 키(추출에 쓰는 것만):

| 키 | 의미 | 추출 용도 |
|---|---|---|
| `type` | 레코드 종류 | `user`/`assistant` 만 처리, 나머지는 무시 |
| `timestamp` | ISO8601 (`...Z`) | 기간 필터(cutoff). 누락/파싱불가 → 보수적으로 제외 |
| `sessionId` | 세션 식별자 | 세션 수 집계 |
| `message` | 메시지 본문 | `content` 를 여기서 꺼냄 |

> **주의**: `type` 에는 메시지 없는 종류가 다수 섞인다 — `attachment`·`queue-operation`·
> `file-history-snapshot`·`last-prompt`·`ai-title`·`system`. 이들은 `message` 가 없으므로
> `type in (user, assistant)` 게이트로 한 번에 걸러진다(스키마가 종류를 추가해도 안전).

## 3. user 레코드 → 프롬프트 추출

`message.content` 는 **문자열 또는 블록 리스트** 둘 다 가능(`user_text` 가 양쪽 처리).

- 문자열: 그대로 사용.
- 리스트: `type == "text"` 블록의 `text` 만 이어붙인다. `tool_result` 등 다른 블록은 무시
  (도구 반환값이 프롬프트로 오염되지 않게 함).

**노이즈 제거** — 하네스가 주입한 텍스트는 진짜 사용자 프롬프트가 아니므로 접두사로 거른다
(`NOISE_PREFIXES`): `<ide_` · `<system-reminder` · `<command` · `<local-command` ·
`<task-` · `<user-` · `[Request interrupted` · `Caveat:`.
→ 새 주입 마커가 생기면 이 목록을 확장해야 집계 정확도가 유지된다.

## 4. assistant 레코드 → 활동 추출

`message.content` 는 블록 리스트. `type == "tool_use"` 블록만 집계한다(`thinking`·`text` 무시).

| 블록 필드 | 집계 |
|---|---|
| `name` | 도구 분포(`tool_use distribution`) |
| `name ∈ {Edit, Write, NotebookEdit}` + `input.file_path` | 파일 basename 빈도 + 디렉터리 핫스팟 |
| `name ∈ {Bash, PowerShell}` + `input.command` | 복합 명령 분리 후 각 세그먼트 정규화·빈도 |

- **복합 명령 분리**(`normalize_cmds`): 한 줄에 체인된 명령(`cd x && git commit`, `a; b`,
  `a || b`)을 `&&`/`||`/`;` 로 나눠 **각 세그먼트를 따로 집계**한다(첫 토큰만 세면 `cd` 같은
  내비게이션이 핫스팟을 오염시키기 때문). 순수 셸 빌트인(`cd`·`export`·`set`·`source` 등)과 빈
  세그먼트는 "명령 실행"이 아니므로 제외. 파이프(`|`)는 분리하지 않는다(하나의 파이프라인).
- **세그먼트 정규화**(`normalize_cmd`, 프로젝트 비종속): 선행 `VAR=val` env 할당 스킵
  (`^\w+=`) → 실행파일 basename(`/usr/bin/python3` → `python3`) → `SUBCOMMAND_TOOLS`
  (git·docker·uv 등)면 비-플래그 서브토큰 1개 유지(`git commit`). 미등록 도구도 basename 으로
  정상 그룹화.
- **디렉터리 핫스팟**(`hotspot_dir`, 프로젝트 비종속): 파일 경로 부모 디렉터리의 **끝 2 세그먼트**
  (`.../src/api/x.py` → `src/api`). 드라이브 접두사(`c:`)는 제거. 프로젝트 루트를 몰라도 핫스팟이
  드러나도록 고정 정규식 대신 데이터에서 도출.

## 5. 기간 필터 (2단)

1. **mtime 사전 필터**: cutoff 이전에 마지막 수정된 `*.jsonl` 은 조기 배제(누적 히스토리 전체
   재판독 회피). 새 레코드가 추가되면 mtime 이 갱신되므로 안전 측.
2. **레코드 ts 필터**: 각 레코드의 `timestamp` 를 cutoff 와 재비교(경계 정밀화). 날짜 미상 레코드는
   집계 부풀림을 막기 위해 제외.

## 6. 의존 패키지

표준 라이브러리만: `argparse`·`glob`·`json`·`os`·`re`·`collections.Counter`·`datetime`.
추가 설치 불필요(어떤 프로젝트 환경에서도 `python3` 만 있으면 실행). 입력은 Claude Code 가
기록하는 위 JSONL 뿐 — 별도 API·DB·네트워크 의존 없음.
