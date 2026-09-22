# 수동 검증

[English](manual-verification.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

필요할 때 직접 부르는 스킬 셋 — 어느 것도 게이트가 아니고, 승격 전에 자동으로 돌지도 않음.

## `/integration`

```text
/integration
```

프로젝트의 기존 통합 스위트를 결정론적으로 돌리거나, 없으면 사람에게서 시나리오를
받음. `/harness-init` 이 만든 `docs/verification/integration.md` 가 있으면 먼저 읽음;
없으면 자체 web/non-web 레퍼런스로 돌아감.

Electron 을 먼저 확인하고, 다음 web, 마지막 non-web 으로 판정함:

| 판정 | 조건 |
|------|------|
| Electron | `"electron"` 의존성이 있음 |
| Web | Electron 신호 없음, 그리고 허용목록 프레임워크 의존성이나 보조 신호(`index.html`, 번들러 설정, `public/`) 중 하나 — 그래서 프레임워크 없는 웹앱도 Web 으로 남음 |
| Non-web | CLI/React Native/Flutter/Go 신호가 있거나, 위 어느 것도 매칭 안 됨 |

- **Web** — 기존 Playwright 케이스를 `--reporter=json` 으로 돌려 PASS/FAIL 을 보고하고
  `results.json`/`results.xml` 을 씀. 케이스 0 개면 인라인으로 스캐폴딩하지 않고
  [`playwright-scaffold`](#playwright-scaffold) 로 넘김. 설정에 선언된 `testDir` 가
  존재하지 않으면 스캐폴딩하지 않고 설정 오류로 보고함.
- **Electron** — 렌더러는 Playwright 로 자동 실행되고, 메인 프로세스는 사람이 진행하는
  체크리스트이며, 두 결과를 함께 보고함.
- **Non-web** — 프로젝트 유형별(CLI, React Native, Flutter, Go)로 시나리오와 통과 기준을
  물음.

## `/performance`

```text
/performance
```

`docs/verification/performance.md` 가 있으면 먼저 읽음; 없으면 내장 카탈로그로 대체함
(Go 의 N+1 패턴만은 전용 카탈로그가 없음).

- **정적 플래깅** — 언어별 안티패턴(N+1 쿼리, 나쁜 쿼리 플랜, 프론트엔드 리렌더
  churn)과, 언어 무관 재귀/복잡도 검사인 `lizard` — 이건 항상 돌림.
- **API 부하 테스트**(백엔드가 있을 때) — 부하를 걸기 전 `AskUserQuestion` 으로
  `BASE_URL` 을 확인함(추측한 URL 은 잘못된 호스트를 때리고, 서버는 이미 떠 있어야 함);
  SLO 대비 p50/p95/p99, throughput, 에러율을 보고함. 기본 도구는 k6 와
  `openapi-to-k6`; 둘 다 AGPL 이므로 `oha`·`autocannon`·`vegeta` 가 MIT 대체임.

여기서 도구를 자동으로 설치하지 않음 — `lizard`·`k6`·`openapi-to-k6` 는 안내만 하고,
환경에 무엇을 받을지는 사용자의 선택임.

## `playwright-scaffold`

```text
/playwright-scaffold
```

케이스가 0개인 웹 프로젝트에 첫 Playwright 케이스를 멱등적으로 만듦 — 보통은 직접
부르기보다 `/integration` 이 호출함.

1. **`baseURL` 감지** — `playwright.config.*` 나 다른 설정 파일에서, 또는 확인을 요청함.
2. **`testDir` 와 언어 감지** — `tsconfig.json` 이 없어도 `playwright.config.ts` 가
   있으면 TypeScript 로 침. 그래서 TS 전용 Playwright 프로젝트도 `.ts` 스펙을 받음.
3. **작성** — 아무것도 없을 때만 `<testDir>/main.smoke.spec.<ts|js>` 를 씀:
   `goto('/')` + 응답 OK + 비어있지 않은 title, 하드코딩된 URL 대신 `use.baseURL` 을 씀.
   설정에 선언된 `testDir` 가 존재하지 않으면 만들지 않고 보고만 함.
4. **`playwright.config` 정리** — `use.baseURL` 이 없는 기존 설정에 추가하거나, 설정이
   아예 없으면 최소 설정을 씀; 모노레포에 필요한 `projects[]` 형태를 보고함.
   `@playwright/test` 자체가 없으면 묻지 않고 실행하는 대신 설치를 안내함.

파일만 쓸 뿐 — 스위트를 돌리는 건 `/integration` 의 몫임.
