# 비웹 통합 테스트 — human-in-the-loop + 참고 OSS

> 비웹 프로젝트에서는 통합 테스트 자동화를 **강제하지 않는다**.
> 이 문서는 타입별 감지 신호, human-in-the-loop 절차, 그리고 자유롭게 선택 가능한
> 참고 OSS(모두 Apache-2.0)를 안내한다.

---

## 1. 비웹 타입별 신호

| 타입 | 감지 신호 | 비고 |
|---|---|---|
| **CLI 도구** | `package.json` 내 `"bin"` 필드 존재 | Node.js CLI |
| | `main.go` + `cobra`/`urfave/cli` 의존성 | Go CLI |
| | `pyproject.toml` 내 `[project.scripts]` 또는 `setup.py`의 `entry_points` | Python CLI |
| **React Native** | `"react-native"` 의존성 | iOS/Android 앱 |
| | `metro.config.js` 존재 | RN 번들러 신호 |
| **Flutter** | `pubspec.yaml` 존재 | iOS/Android/Desktop |
| **Electron** | `"electron"` 의존성 | 데스크톱 앱 (예외 있음) |
| **Go 서비스/CLI** | `go.mod` + 웹 프레임워크 의존성 없음 | HTTP 서버가 있어도 프론트 없으면 비웹 |
| **Python 서비스** | `pyproject.toml`/`requirements.txt` + 웹 프레임워크 의존성 없음 | FastAPI·Django는 백엔드 — 웹 프론트와 구분 |

> **Electron 예외**: `"electron"` 의존성이 있더라도, Chromium 렌더러 프로세스는
> `playwright chromium`으로 부분 자동화가 가능하다.
> Electron 앱의 통합 테스트는 [`web-playwright.md`](web-playwright.md) "Electron 예외" 절을 참조하고,
> 주 프로세스(IPC·파일시스템·네이티브 API) 관련 시나리오만 human-in-the-loop으로 처리한다.

---

## 2. human-in-the-loop 절차

비웹으로 판정된 경우, `AskUserQuestion`으로 아래 항목을 수집한다.

### 2.1 수집 항목

```
이 프로젝트는 비웹(<타입>)으로 감지되었습니다.
통합 테스트 자동화 도구를 강제하지 않습니다.

아래 항목을 알려주세요:

1. 검증할 핵심 시나리오
   예: "사용자 로그인 후 데이터 조회", "파일 업로드 후 변환 결과 확인"

2. 각 시나리오의 통과 기준
   예: "응답 코드 200 + body에 id 필드 포함", "변환 파일이 ./output/에 생성됨"

3. 현재 사용 중인 테스트 도구 (있다면)
   예: "Newman으로 Postman 컬렉션 실행 중", "없음"

4. 자동화 우선순위
   예: "API 엔드포인트 계약 테스트 먼저", "수동 체크리스트로 충분"
```

### 2.2 수집 후 처리

수집한 시나리오를 기반으로 **수동 검증 체크리스트**를 작성한다:

```markdown
## 통합 검증 체크리스트 — <날짜>

### 시나리오 1: <시나리오명>
- [ ] 전제 조건: ...
- [ ] 실행 단계: ...
- [ ] 통과 기준: ...
- [ ] 실제 결과: (수동 입력)
- [ ] 판정: PASS / FAIL

### 판정 요약
| 시나리오 | 판정 |
|---|---|
| <시나리오 1> | PASS |
| <시나리오 2> | FAIL |

**전체 판정**: FAIL (1건 실패)
```

---

## 3. 참고 OSS (자동 강제 안 함)

아래 도구는 비웹 통합 테스트에 활용할 수 있는 무료·상용가능 OSS다.
이 스킬은 도구를 **자동으로 설치·실행하지 않는다** — 안내만 제공한다.

### 3.1 Newman (API 계약 테스트)

출처: https://github.com/postmanlabs/newman (Apache-2.0)

Postman 컬렉션을 CLI로 실행하는 도구다. REST API 계약 테스트에 적합하다.

```bash
# 설치
npm install -g newman

# Postman 컬렉션 실행
newman run collection.json -e environment.json --reporters cli,junit --reporter-junit-export results.xml
```

**적합 시나리오**: REST API 엔드포인트 계약 검증, CI 파이프라인 통합.

### 3.2 Maestro (모바일 UI 테스트)

출처: https://maestro.dev/ · https://github.com/mobile-dev-inc/maestro (Apache-2.0)

React Native·Flutter·iOS·Android 앱의 UI 흐름을 YAML로 정의해 실행한다.

```yaml
# example: login-flow.yaml
appId: com.example.myapp
---
- launchApp
- tapOn: "이메일 입력"
- inputText: "test@example.com"
- tapOn: "로그인"
- assertVisible: "홈 화면"
```

```bash
# 실행
maestro test login-flow.yaml
```

**적합 시나리오**: React Native·Flutter 앱 핵심 UI 흐름 검증.

### 3.3 Appium (크로스플랫폼 모바일 자동화)

출처: https://github.com/appium/appium (Apache-2.0)

iOS·Android·Windows·macOS를 WebDriver 프로토콜로 자동화한다. 러닝커브가 높지만
범용성이 가장 높다.

```bash
# 설치
npm install -g appium
appium driver install uiautomator2   # Android
appium driver install xcuitest       # iOS

# 서버 시작
appium
```

**적합 시나리오**: 플랫폼 간 통합이 필요한 모바일 앱, 네이티브 요소 제어가 필요한 경우.

---

## 4. 비웹 타입별 권장 접근

| 타입 | 권장 접근 | 참고 도구 |
|---|---|---|
| CLI 도구 | 표준 입출력·종료 코드 테스트 | `pytest`·Go `testing`·Jest |
| REST API 서비스 (프론트 없음) | Postman 컬렉션 → Newman CI 실행 | Newman (Apache-2.0) |
| React Native | Maestro YAML 흐름 정의 | Maestro (Apache-2.0) |
| Flutter | `flutter test` 통합 테스트 + Maestro | Maestro (Apache-2.0) |
| Electron (렌더러) | Playwright chromium 채널 | [`web-playwright.md`](web-playwright.md) |
| Electron (주 프로세스·IPC) | human-in-the-loop 수동 체크리스트 | — |
| iOS/Android 네이티브 | Appium WebDriver | Appium (Apache-2.0) |

---

## 5. SSOT URL 요약

| 항목 | URL | 라이선스 |
|---|---|---|
| Newman | https://github.com/postmanlabs/newman | Apache-2.0 |
| Maestro | https://maestro.dev/ | Apache-2.0 |
| Maestro GitHub | https://github.com/mobile-dev-inc/maestro | Apache-2.0 |
| Appium | https://github.com/appium/appium | Apache-2.0 |
