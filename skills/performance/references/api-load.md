# OpenAPI 발견 + API 부하 측정 + 리포트 표준

> SSOT: 스펙 §10.5~§10.6 사전 리서치 기준 (2026-06). 출처 URL·라이선스 명시.

---

## 1. OpenAPI 스펙 자동 발견

### 1.1 후보 경로 순서

서버가 실행 중이라면 아래 순서로 GET한다. 첫 성공 응답을 사용한다.

| 우선순위 | 경로 | 프레임워크 | 출처 |
|---|---|---|---|
| 1 | `/openapi.json` | FastAPI | https://fastapi.tiangolo.com/tutorial/metadata/ |
| 2 | `/v3/api-docs` | springdoc-openapi | https://github.com/springdoc/springdoc-openapi |
| 3 | `/swagger/v1/swagger.json` | ASP.NET Swashbuckle (documentName 기본 `v1`) | https://learn.microsoft.com/en-us/aspnet/core/tutorials/getting-started-with-swashbuckle |
| 4 | `/swagger.json` | 일반 관례 | — |
| 5 | `/api-docs` | 일반 관례 | — |

**ASP.NET documentName 가변 처리**: `/swagger/v1/swagger.json` 실패 시 `/swagger` HTML을
가져와 `<script>` 내 `url: "..."` 패턴을 파싱해 실제 spec URL을 추출한다.

```bash
# 자동 발견 스크립트 (bash)
BASE_URL="${1:-http://localhost:8000}"
SPEC_URL=""
for path in /openapi.json /v3/api-docs /swagger/v1/swagger.json /swagger.json /api-docs; do
  if curl -sf "${BASE_URL}${path}" -o /tmp/openapi_spec.json; then
    SPEC_URL="${BASE_URL}${path}"
    echo "spec found: ${SPEC_URL}"
    break
  fi
done
if [ -z "$SPEC_URL" ]; then
  echo "OpenAPI spec not found — check server is running and spec endpoint is enabled"
  exit 1
fi
```

### 1.2 $ref dereference

`$ref`가 있는 spec은 도구 처리 전 resolve가 필요할 수 있다.

| 도구 | 라이선스 | 용도 | 출처 |
|---|---|---|---|
| prance | MIT | Python — $ref resolve + 유효성 검사 | https://github.com/RonnyPfannschmidt/prance |
| schemathesis | MIT | $ref resolve + contract 테스트 | https://github.com/schemathesis/schemathesis |
| json-schema-faker | MIT | example 값 생성 (JS) | https://github.com/json-schema-faker/json-schema-faker |

### 1.3 example 값 override 규칙

OpenAPI 3.1.1 스펙 기준:

- 필드 레벨 `example` (단수) → 단일 예제값.
- 필드 레벨 `examples` (복수) → 이름 키: `{ value, summary }` 맵.
- 부하 테스트 시 `examples` 중 첫 번째(또는 `default` 키)를 우선 사용.
- `$ref`로 참조된 schema의 example은 참조 해석 후 오버라이드 가능.

출처: https://spec.openapis.org/oas/v3.1.1.html · 3.0→3.1 업그레이드: https://learn.openapis.org/upgrading/v3.0-to-v3.1.html

---

## 2. 부하 도구

### 2.1 1순위: openapi-to-k6 + k6 (AGPL-3.0)

> **라이선스 주의**: openapi-to-k6와 k6는 모두 **AGPL-3.0**이다.
> - **내부 CI/개발 환경 사용**: 무해. AGPL은 내부 사용 시 소스 공개 의무 없음.
> - **회피해야 하는 경우**: 도구 자체를 재배포하거나 SaaS로 호스팅할 때.
> 일반적인 팀 내부 성능 점검 목적이라면 AGPL-3.0 도구를 사용해도 된다.

| 도구 | 버전 확인 | 출처 |
|---|---|---|
| openapi-to-k6 | `npx openapi-to-k6 --version` | https://github.com/grafana/openapi-to-k6 |
| k6 | `k6 version` | https://grafana.com/docs/k6/latest/ |

**설치 (없을 경우):**
```bash
# openapi-to-k6 (npx 즉시 사용 가능)
npm install -g @grafana/openapi-to-k6  # 또는 npx 직접

# k6 (OS별)
# macOS: brew install k6
# Linux: https://grafana.com/docs/k6/latest/set-up/install-k6/
# Windows: choco install k6  또는 공식 MSI
```

**실행 (각 엔드포인트 100회):**

> ⚠️ `k6 run --iterations N`은 **스크립트 전체** 실행 횟수이지 엔드포인트별 횟수가 **아니다**.
> 엔드포인트가 여러 개이면 단순 `--iterations 100`은 "각 API 100회"를 **보장하지 않는다**.
> **각 엔드포인트를 정확히 100회** 측정하려면 k6 **scenarios**로 엔드포인트마다 별도
> 시나리오(`iterations: 100`)를 둔다. openapi-to-k6가 operation별 함수를 생성하므로
> 그 함수를 시나리오 `exec`에 연결한다.

```bash
# 1) OpenAPI → k6 클라이언트(operation별 함수) 생성
npx openapi-to-k6 /tmp/openapi_spec.json -o /tmp/k6-client.js
```

```javascript
// /tmp/k6-load.js — 엔드포인트별 시나리오(각 100 iterations)
import { getUsers, createOrder } from './k6-client.js'; // openapi-to-k6 생성 함수
export const options = {
  scenarios: {
    get_users:    { executor: 'per-vu-iterations', vus: 10, iterations: 100, exec: 'getUsers' },
    create_order: { executor: 'per-vu-iterations', vus: 10, iterations: 100, exec: 'createOrder' },
  },
};
export function getUsers()    { /* 생성 클라이언트로 GET /users 호출 */ }
export function createOrder() { /* 생성 클라이언트로 POST /orders 호출 */ }
```

```bash
# 2) 실행 + JSON 결과 (엔드포인트별 100회)
k6 run --out json=/tmp/k6-result.json /tmp/k6-load.js
```

> 엔드포인트가 많으면 위 `scenarios` 를 스펙의 (method, path) 목록에서 **프로그램으로 생성**한다.
> 단일 엔드포인트뿐이면 `k6 run --iterations 100`로 충분하다(그때만 전체=엔드포인트).

### 2.2 MIT 폴백 (AGPL 회피 시)

| 도구 | 라이선스 | 특징 | 출처 |
|---|---|---|---|
| oha | MIT | Rust 구현, JSON 출력 지원 (`-j`), schema 유사 지표 | https://github.com/hatoo/oha |
| autocannon | MIT | Node.js, JSON 출력, p99 지원 | https://github.com/mcollina/autocannon |
| vegeta | MIT | targets 파일로 다중 엔드포인트, JSON 리포트 | https://github.com/tsenart/vegeta |

**oha 예 (엔드포인트 직접 순회):**
```bash
# 각 엔드포인트 100회
oha -n 100 -c 10 -j http://localhost:8000/users > /tmp/oha-users.json
oha -n 100 -c 10 -j http://localhost:8000/orders > /tmp/oha-orders.json
```

**vegeta 예 (targets 파일):**
```bash
# targets.txt
echo "GET http://localhost:8000/users" >> targets.txt
echo "GET http://localhost:8000/orders" >> targets.txt

vegeta attack -targets=targets.txt -rate=10 -duration=10s \
  | vegeta encode --to=json \
  | vegeta report --type=json > /tmp/vegeta-result.json
```

### 2.3 참고: 단순 단일 URL 도구 (p99 미지원 등 — 권장 안 함)

| 도구 | 라이선스 | 한계 | 출처 |
|---|---|---|---|
| hey | Apache-2.0 | CSV 출력만, p99 미지원 | https://github.com/rakyll/hey |
| wrk | Apache-2.0 | p95 미제공, Lua 스크립트 필요 | https://github.com/wg/wrk |
| ab (Apache Bench) | Apache-2.0 | 단일 URL, 통계 제한 | https://httpd.apache.org/docs/2.4/programs/ab.html |

---

## 3. 리포트 표준

### 3.1 필수 지표 (평균 단독 금지)

> **원칙**: 평균(mean/avg)은 롱테일을 숨긴다. 반드시 백분위 분포를 함께 보고한다.
> 백분위는 평균 내지 않는다(비가산성) — 집계 레벨에 따라 백분위가 달라지므로
> 개별 요청 레벨에서만 계산한다.
>
> 출처: https://orangematter.solarwinds.com/2016/11/18/why-percentiles-dont-work-the-way-you-think/

| 지표 | 설명 | 필수 |
|---|---|---|
| p50 (중앙값) | 절반의 요청이 이 이하 | ✓ |
| p95 | 95%의 요청이 이 이하 | ✓ |
| p99 | 99%의 요청이 이 이하 | ✓ |
| p99.9 | 99.9%의 요청이 이 이하 (롱테일 포착) | 권장 |
| throughput (RPS) | 초당 처리 요청 수 | ✓ |
| VU (동시성) | 동시 가상 사용자 수 | ✓ |
| 에러율 | 5xx·연결 실패 비율 (%) | ✓ |
| **SLO 대비 PASS/FAIL** | 사전 정의 SLO와 비교한 판정 | ✓ |

SLO 참고: https://sre.google/sre-book/service-level-objectives/

### 3.2 Four Golden Signals 골격

출처: https://sre.google/sre-book/monitoring-distributed-systems/

```
### Golden Signals 요약
- **Latency (지연)**: p50 / p95 / p99 / p99.9 — SLO 기준 PASS/FAIL
- **Traffic (트래픽)**: RPS·VU·부하 모델(constant/ramp-up/spike)
- **Errors (에러율)**: 에러율 % · 에러 종류(5xx/4xx/timeout)
- **Saturation (포화도)**: CPU·메모리 측정 가능 시 기록 (선택)
```

### 3.3 측정 메타 (필수 기록)

```
측정 메타:
- 도구·버전: openapi-to-k6 x.y.z + k6 0.52.x
- 부하 모델: constant / ramp-up / spike
- 지속시간: Xs (또는 iterations=100 per endpoint)
- VU (동시성): N
- warm-up 제외: 첫 M회 제외 여부 명시
- CO(Coordinated Omission) 보정: 적용/미적용 명시
- 실행 환경: 로컬 / CI / 네트워크 오버헤드 유무
```

### 3.4 통계 관례

#### warm-up 제외

JVM·JIT·커넥션풀 초기화로 첫 요청이 느리다. warm-up 구간을 결과에서 제거한다.
출처: https://www.azul.com/blog/ramps-in-performance-tests-best-practices/

#### Coordinated Omission (CO) 보정

클라이언트가 응답 대기 중 다음 요청을 보내지 않으면, 느린 응답이 숨겨진다.
HdrHistogram 기반 CO 보정이 가능한 도구(k6의 일부 설정, vegeta)를 사용하면 실제 지연 분포를
더 정확히 측정한다. 보정 여부를 반드시 메타에 명시한다.
출처: https://github.com/HdrHistogram/HdrHistogram

The Tail at Scale 참고(고백분위 중요성): https://cacm.acm.org/research/the-tail-at-scale/

#### 백분위 비가산성

서비스 A의 p99 + 서비스 B의 p99 ≠ 전체 p99. 요청 레벨 데이터에서 직접 집계해야 한다.
출처: https://orangematter.solarwinds.com/2016/11/18/why-percentiles-dont-work-the-way-you-think/

### 3.5 리포트 템플릿

```markdown
## API 부하 측정 결과 — <날짜>

**측정 메타**
- 도구: openapi-to-k6 <버전> + k6 <버전>
- 부하 모델: constant / iterations=100 per endpoint
- VU: 10 / warm-up: 첫 10회 제외 / CO 보정: 미적용
- 환경: 로컬 (서버: localhost:8000)

**SLO 기준**
| 엔드포인트 | p99 SLO | 에러율 SLO |
|---|---|---|
| 전체 | ≤ 500ms | ≤ 1% |

**결과**
| 엔드포인트 | p50 | p95 | p99 | p99.9 | RPS | VU | 에러율 | SLO 판정 |
|---|---|---|---|---|---|---|---|---|
| GET /users | 12ms | 45ms | 120ms | 350ms | 850 | 10 | 0.0% | PASS |
| POST /orders | 80ms | 350ms | 890ms | 2100ms | 210 | 10 | 1.2% | FAIL |

**Golden Signals**
- Latency: POST /orders p99 890ms > SLO 500ms ← **주목**
- Traffic: RPS 850 (GET) / 210 (POST)
- Errors: POST /orders 1.2% 에러율 > SLO 1%
- Saturation: 측정 안 함

**권고**
- POST /orders: p99 초과 — 쿼리 플랜 확인 및 DB 인덱스 추가 검토
- POST /orders: 에러율 초과 — 5xx 로그 확인
```

---

## 4. 라이선스 요약

| 도구 | 라이선스 | 내부 CI 사용 | 재배포/SaaS |
|---|---|---|---|
| openapi-to-k6 | AGPL-3.0 | 무해 | 회피 필요 |
| k6 | AGPL-3.0 | 무해 | 회피 필요 |
| oha | MIT | 무해 | 무해 |
| autocannon | MIT | 무해 | 무해 |
| vegeta | MIT | 무해 | 무해 |
| prance | MIT | 무해 | 무해 |
| schemathesis | MIT | 무해 | 무해 |
| json-schema-faker | MIT | 무해 | 무해 |
| hey | Apache-2.0 | 무해 | 무해 |
| wrk | Apache-2.0 | 무해 | 무해 |
| ab | Apache-2.0 | 무해 | 무해 |
