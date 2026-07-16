# 사용자 정의 런타임 게이트(모듈 커스텀 검사) — 설계

- **Date**: 2026-07-15
- **Status**: Approved (brainstorming) → pending implementation plan
- **Scope**: harness-tier 플러그인(소비자에 배포되는 SSOT 템플릿·게이트 스크립트) — 강제 범위는 기존 layer-2 flow 게이트와 동일

## 1. 목표

호스트 개발자가 **자기만의 런타임 게이트(커밋 시 자동 실행되는 검사 명령)** 를 추가할 수 있게 한다.
예: `license-check`, `secret-scan`, `sbom`. 통과하면 커밋, 실패하면 차단.

핵심 제약: 티어→게이트 매핑을 담은 `flow-tiers.yaml`은 **플러그인 소유·불변·재설치 때 덮어써짐**이므로
사용자 확장은 반드시 **호스트 소유 파일(`flow-config.yaml`)** 안에서 살아남아야 한다. 그리고 각 커스텀
검사는 **언제(타이밍)** 도는지를 스스로 선언한다.

## 2. 배경 — 현재 상태

- **런타임 게이트는 마커(`.done`) 시스템과 완전히 분리**돼 있다. `precommit-runner.sh`(PreToolUse 훅)는
  `flow_gate_check.py --module-commands`가 stdout으로 내는 명령 목록을 그냥 실행하고, 하나라도
  non-zero면 `deny`(exit 2)한다. 즉 "런타임 게이트 추가" = *현재 티어에서 실행할 명령을 목록에 더 얹기*.
  `flow-tiers.yaml`(불변)을 건드릴 필요가 없다.
- 현재 명령 목록은 `flow-config.modules[].checks`에서 나온다. [`_check_cmds`](../../../scripts/flow_gate_check.py)의
  로직이 결정적이다:
  - `_check_cmds(security=False)` = **`security`가 아닌 모든 키** → `precommit` 게이트(변경 모듈, 매 커밋).
  - `_check_cmds(security=True)` = **`security` 키만** → `security-scan` 게이트(전체 모듈, 승격).
- **결과적으로, "security가 아닌 임의 키"는 이미 매 커밋에 실행된다.** 즉 사용자가 `modules[].checks`에
  `license: "make license-check"`를 추가하면 변경 모듈 커밋에서 이미 돌고 실패 시 차단된다. check 키를
  강제하는 allowlist는 코드/문서 어디에도 없다(키 이름은 주석상 관례일 뿐).
- **남는 진짜 공백 둘**:
  1. *발견 가능성* — `flow-config.example.yaml`·`/flow-init`·USAGE가 키를 고정 어휘
     (`lint/static/import_lint/test/security`)처럼 서술해, 사용자가 "내 키를 추가해도 된다"는 걸 모른다.
  2. *타이밍 제어* — "승격 때만 도는" 커스텀 검사는 지금 `security` 키 **딱 한 슬롯**뿐이라, 승격 전용
     커스텀 검사를 여러 개 깔끔히 넣을 수 없다.

## 3. 결정 사항 (brainstorming)

| 질문 | 결정 |
|------|------|
| 게이트 종류 | **자동 실행 명령(runtime)** — 커밋 시 실행, 실패 시 차단(마커 아님) |
| 실행 범위/위치 | **모듈별** — 기존 `modules[].checks` 확장(별도 최상위 섹션 X) |
| 타이밍 모델 | **게이트별 개별 선택** — 각 검사가 `when: every-commit \| promotion`을 선언 |
| 실행 범위(타이밍 파생) | `every-commit`→**변경 모듈**, `promotion`→**전체 모듈**(기존 security-scan과 동일) |
| `security` 매직 키 | **하위호환 매핑으로 잔존**(의도된 부채) — 문자열 `security`는 `promotion` 기본값 |
| 강제 범위 | **Claude 세션 커밋(layer-2)만** — 터미널/CI 커밋 비강제, 명시 문서화. CI 안전망은 **비목표(후속)** |
| 필드명 | `run`(명령) + `when`(타이밍); 값 `every-commit` \| `promotion`. **`on`이 아니라 `when`** — YAML 1.1이 bare 키 `on`을 불리언 `True`로 파싱해 되읽을 수 없기 때문(구현 중 발견, 승인된 `on`에서 교정). |
| 잘못된 `when` 값 | 런타임 **fail-open** + stderr 경고 + **fail-safe로 every-commit**(더 자주 도는 쪽); 엄격 검증은 `/flow-init` |

## 4. config 스키마 (호스트가 쓰는 면)

`modules[].checks`의 값이 지금은 "명령 문자열"만 된다. 여기에 **확장 형식(dict)** 을 하위호환으로 추가:

```yaml
modules:
  - name: api
    path: services/api/
    checks:
      # ── 기존 형식(문자열) — 그대로 동작 ──
      lint:     "ruff check services/api"      # 문자열 → every-commit (변경 모듈)
      test:     "uv run pytest services/api"    # 〃
      security: "bandit -r services/api"        # 'security' 키만 문자열이어도 promotion 기본값 (하위호환)

      # ── 새 확장 형식(dict) — 사용자 커스텀 게이트 ──
      license:                                   # 임의 이름
        run: "make license-check"
        when: every-commit                      # every-commit | promotion
      sbom:
        run: "syft . -o spdx-json > sbom.json"
        when: promotion                         # 승격(staging/release) 때만, 전체 모듈
```

> **필드명은 `when`(≠ `on`)**: YAML 1.1(PyYAML)은 bare 키 `on`/`off`/`yes`/`no`를 불리언으로 파싱해
> `on: promotion`이 `{True: 'promotion'}`이 된다 → `val.get("on")`이 되읽지 못함. 그래서 `when`을 쓴다
> (구현 중 발견, 승인된 `on`에서 교정).

파싱 규칙(`_parse_check(key, val) -> (command|None, timing, warning|None)`, 순수 함수):
- **값이 문자열/스칼라** → 명령 = `str(val)`. 타이밍 = 키-이름 기본값(`security`→`promotion`, 그 외→`every-commit`).
  = 지금 동작 그대로.
- **값이 dict** → 명령 = `run`, 타이밍 = `when`(`every-commit`|`promotion`). `when` 생략 시 문자열과 같은
  키-이름 기본값. `run` 없음/빈 값 → 명령 None(건너뜀).
- **`when`이 미인식 값**(오타 등) → 타이밍 = `every-commit`(fail-safe: 덜 도는 것보다 자주 도는 게 안전),
  `warning` 반환 → stderr로 노출.

## 5. 타이밍 → 게이트 → 범위 매핑 (강제되는 면)

| 타이밍 | 실행 게이트(`flow-tiers.yaml`) | 실행 범위 | 언제 |
|--------|-------------------------------|-----------|------|
| `every-commit` | `precommit` | **변경된 모듈만** | precommit 게이트가 있는 티어(dev/staging/release)의 매 커밋 |
| `promotion` | `security-scan` | **전체 모듈** | security-scan 게이트가 있는 티어(staging/release)의 승격 커밋 |

- **범위는 타이밍에서 파생**된다(따로 고르지 않음). every-commit=변경 모듈, promotion=전체 모듈.
  이 파생이 기존 `security` 동작을 한 글자도 바꾸지 않는 지점이다.
- **타이밍은 "해당 게이트가 그 티어에 존재하는지"에 종속**된다(§6-A). 이는 한계가 아니라 자연스러운 결과지만
  반드시 문서화한다:
  - `docs` 티어엔 `precommit`이 없고, 게다가 `module_commands`에 `tier == "docs"` **단락**이 명시적으로 있어
    (`flow_gate_check.py:263`), **docs 커밋에는 어떤 커스텀 검사도 걸리지 않는다**(이중 제외). → docs 전용
    커스텀 검사(예: markdown 링크 검사)는 본 설계로는 붙일 수 없음(명시적 한계).
  - `promotion` 커스텀은 `security-scan`이 있는 staging/release에서만 돈다.
- **게이트 on/off 스위치 일반화 유지**: 어떤 티어에서 `security-scan`을 빼면 그 티어의 **모든 promotion
  커스텀 검사**가 꺼지고, `precommit`을 빼면 모든 every-commit 검사가 꺼진다.

## 6. 오류 처리 & 엣지 케이스

- **A. 타이밍은 게이트 존재에 종속(핵심 문서화 항목)** — §5. docs 단락 + 게이트별 on/off. 새 한계 아님이나
  기대와 어긋날 수 있어 risk-tiers Gate glossary에 명시.
- **B. `security` 매직 키 잔존(의도된 부채)** — 완전히 사라지지 않고 `_parse_check`의 키-이름 기본값
  (`key == "security"` → promotion)으로 남는다. 없애려면 기존 config 재작성 마이그레이션이 필요해 남의
  config를 깨뜨리므로 잔존이 옳다. 테스트에 "문자열 `security` → promotion" 하위호환 케이스로 고정.
- **C. 강제 범위 = Claude 세션 커밋만** — `precommit-runner.sh`는 PreToolUse 훅이라 Claude 세션 커밋에만
  발화한다. 터미널 직접 커밋·CI·GitHub 웹 커밋은 이 게이트를 거치지 않는다(기존 layer-2 property 그대로).
  즉 커스텀 검사는 "모두가 반드시 통과"가 아니라 기존 `precommit`과 **동일한 best-effort 강제**다. 이 범위를
  risk-tiers/USAGE에 정직하게 명시. **사용자 결정(2026-07-15): 세션 커밋 강제로 충분**, 터미널/CI 강제를
  위한 CI 안전망 렌더링은 **비목표**(후속 가능).
- **D. 잘못된 `when` 값 → 조용한 오배치 방지** — 미인식 `when`(오타)이면 promotion 의도 검사가 조용히
  every-commit로 떨어질 수 있다. 런타임은 Invariant #1대로 fail-open을 유지하되 **stderr 1줄 경고 + fail-safe
  every-commit**(자주 도는 쪽)으로 처리. 엄격 검증(값 화이트리스트·`run` 누락 감지)은 `/flow-init`에서.
  경고는 `module_commands`가 `report`(stderr)로 모아 노출(중복 제거).
- **E. Invariant 보존** — #1 FAIL-OPEN(잘못된 checks/config → 건너뜀, `module_commands`의 기존 예외 처리와
  동일; 강한 fail-closed는 미분류 커밋·python/PyYAML 부재에만). #2 cp949 UTF-8 방어(`module_commands_output`이
  이미 `force_utf8_io` 호출 — 새 print 경로도 이 뒤). #3 exit-2 차단 불변.
- **F. `precommit-runner.sh` 무변경** — 러너는 "명령 실행 → 실패 시 deny"의 완전 제네릭 실행기라
  스키마 확장의 영향을 받지 않는다. 커스텀 명령도 같은 stdout 스트림으로 흘러 그대로 실행됨. 빈 명령
  early-exit(`[ -n "$mod_cmds" ]`)도 유지(커스텀 명령이 있으면 통과).
- **G. 순서/결정성** — dict 반복 순서 = 삽입 순서(Python 3.7+/YAML 보존). 명령 실행 순서 결정적.
- **H. 언어** — 새 사용자 노출 문자열(경고 등)은 기존 관례(host 응답 언어; 영어 기본, `flow_gate_check.py`
  선례)를 재사용. 새 i18n 메커니즘 없음.

## 7. 컴포넌트 & 변경

| # | 파일 | 변경 | 종류 |
|---|------|------|------|
| 1 | `scripts/flow_gate_check.py` | `_check_cmds(mod, *, security)` → `promotion`으로 일반화(반환 `(cmds, warnings)`), `_parse_check`/`_default_timing` 헬퍼 추가; `module_commands` 두 호출부 `security=`→`promotion=` + 경고를 `report`에 병합 | 코드 |
| 2 | `scripts/precommit-runner.sh` | **무변경**(제네릭 실행기). 헤더 주석의 "lint/static/import_lint/test" 문구만 선택적 정정 | (검증) |
| 3 | `scripts/_harness_paths.py` | `RUNTIME_GATES` 주석을 "타이밍 버킷(every-commit/promotion)"으로 일반화. 튜플 값(`precommit`,`security-scan`)은 무변경 | 주석 |
| 4 | `flow-config.example.yaml` | `checks` 주석(고정 어휘 뉘앙스·Timing 노트) 정정 + 확장 형식(dict `{run,on}`) 커스텀 검사 예시 추가 | 설정 템플릿 |
| 5 | `flow-tiers.yaml` | dev/staging description 문구 소폭 정정(선택; 정책 매핑은 무변경) | 정책(설명만) |
| 6 | `skills/flow-init/SKILL.md` | 모듈 checks 추론 지침에 "커스텀 키 + `{run,when}` 형식 지원" 반영 + `when` 값 검증/경고 지침(every-commit\|promotion) | 스킬 |
| 7 | `rules/risk-tiers.md` | Gate glossary에서 `precommit`/`security-scan`을 "타이밍 버킷"으로 서술 + "타이밍은 해당 게이트 존재에 종속(docs 단락)" 명시 + 커스텀 확장 방법 1줄 + 세션-커밋 강제 범위 재확인 | 룰(SSOT, `feat` 전파) |
| 8 | `USAGE.md` / `USAGE.ko.md` | 게이트 표를 "임의 키 + 검사별 타이밍(every-commit→변경 모듈 / promotion→전체 모듈)"으로 일반화 | 문서 |
| 9 | `tests/test_flow_gate_check.py` | 확장 파싱·타이밍 라우팅·하위호환·`when` 생략·잘못된 `when`·promotion 다개·docs 단락 회귀 | 테스트 |

- `scripts/flow_init_setup.py`: 신규 파일 없음 → COPY_FILES 변경 불필요. 변경된 `flow_gate_check.py`는 기존
  복사 목록에 그대로 편승(재설치/`/flow-init` 재실행으로 호스트 반영).
- (선택·후속) `rules/harness-rules.md`·`skills/harness-authoring/references/tech-doc-guide.md`의 check-키 어휘
  서술 — `/harness-init` 생성 문서도 커스텀 검사를 언급하도록 손볼 수 있으나 본 스펙 범위 밖(가벼운 후속).

## 8. 테스트 전략

1. **파싱 단위** — `_parse_check`: 문자열/ dict/`when` 생략/미인식 `when`(경고+every-commit)/`run` 누락(None) 각각.
2. **타이밍 라우팅** — `module_commands`(pytest, tmp config): every-commit 검사 → 변경 모듈에서만 emit;
   promotion 검사 → 전체 모듈에서 emit; 동일 커밋이 staging이면 both.
3. **하위호환(회귀 가드)** — 문자열 `security` → promotion(전체 모듈); 문자열 기타 키 → every-commit(변경 모듈);
   기존 example config가 동일 명령 집합을 낸다.
4. **다개 promotion** — 한 모듈에 `security` + `when: promotion` 커스텀 2개 → 셋 다 security-scan에서 emit.
5. **docs 단락** — docs 티어에서는 커스텀 검사가 하나도 emit되지 않음.
6. **경고 노출** — 미인식 `when`이 `module_commands`의 stderr report에 1줄로 들어가고 명령은 fail-safe로 emit됨.
7. **정적 분석** — `precommit-runner.sh`를 만졌다면 ShellCheck(훅 런타임 Windows — 필수); 전체 `pre-commit`
   (ruff/gitlint/…) 통과. `uv run pytest` 그린.

## 9. 롤아웃 / 전파

이 레포는 플러그인 자체 → 변경이 자동으로 어디서나 라이브가 아니다.

1. **`feat`로 릴리스** — `plugin.json` version 범프(Explicit-version 게이팅; `docs`/`chore`는 소비자 전파 안 됨).
   consumer 동작(커스텀 게이트 인식·risk-tiers 서술)을 바꾸므로 risk-tiers Commit Discipline상 `feat` 필수.
2. **소비자는 `/flow-init` 재실행** — 호스트의 게이트 스크립트 복사본 갱신(변경된 `flow_gate_check.py`). config는
   유지. `.md` 룰/스킬 갱신은 플러그인 업데이트에 편승.
3. **하위호환** — 기존 host `flow-config.yaml`은 그대로 동작(§6-B, §8-3). 재설치만으로 새 확장 형식 사용 가능.

## 10. 오픈 항목 / 후속

- **CI 안전망**(터미널/CI 커밋에도 커스텀 검사 강제) — 비목표. 필요 시 `unit_test.yml` 패턴처럼 별도 CI 렌더링
  + flow-config 스키마 확장 + 하네스-tier 자체 CI 적용(메모리 규칙)으로 후속 설계.
- **검사별 독립 범위**(예: promotion + 변경 모듈 조합) — 미지원(범위는 타이밍 파생). YAGNI, 후속 가능.
- **docs 전용 커스텀 검사** — 본 설계로 불가(§6-A). 필요가 생기면 docs 단락 완화를 별도 검토.
- **harness-authoring 문서 어휘**(§7 선택 항목) — `/harness-init` 생성 문서의 커스텀 검사 언급 여부.
