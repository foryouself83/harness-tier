# OpenAPI Discovery + API Load Testing + Report Standard

> SSOT: based on the §10.5–§10.6 preliminary research from the spec (2026-06). Source URLs and licenses are cited.

---

## 1. Automatic OpenAPI Spec Discovery + BASE_URL Confirmation

### 1.1 BASE_URL Detection (multi-source, with required user confirmation)

Do not hardcode or silently default BASE_URL. Gather candidates, then **confirm with the user** before use
(same principle as `playwright-scaffold`'s baseURL detection):

```bash
# 1) flow-config.yaml (host-shared config, if this project uses the harness-tier flow)
grep -A2 "contract_test:" .claude/harness-tier/config/flow-config.yaml 2>/dev/null | grep "base_url"

# 2) docker-compose port mapping (backend service host port)
grep -nE '^\s*-\s*"?[0-9]+:[0-9]+' docker-compose.y*ml compose.y*ml 2>/dev/null

# 3) PORT / BASE_URL in .env
grep -nhE '^(PORT|BASE_URL)=' .env .env.* 2>/dev/null

# 4) framework-default ports (if nothing above matched)
#    FastAPI/Django=8000, Spring Boot=8080, ASP.NET=5000/7000, Rails/Express=3000
```

**User confirmation (required)**: present the collected candidates via `AskUserQuestion` and finalize
`BASE_URL` (offer them as choices if there are several; ask for direct input if none was found). Do not
assert a guess as fact — this mirrors `playwright-scaffold`'s Step 1 exactly.

### 1.2 Candidate-Path Order

If the server is running, GET the paths below in order using the confirmed `BASE_URL`. Use the first
successful response.

| Priority | Path | Framework | Source |
|---|---|---|---|
| 1 | `/openapi.json` | FastAPI | https://fastapi.tiangolo.com/tutorial/metadata/ |
| 2 | `/v3/api-docs` | springdoc-openapi | https://github.com/springdoc/springdoc-openapi |
| 3 | `/swagger/v1/swagger.json` | ASP.NET Swashbuckle (default documentName `v1`) | https://learn.microsoft.com/en-us/aspnet/core/tutorials/getting-started-with-swashbuckle |
| 4 | `/swagger.json` | Common convention | — |
| 5 | `/api-docs` | Common convention | — |

**Handling the variable ASP.NET documentName**: if `/swagger/v1/swagger.json` fails, fetch the
`/swagger` HTML and parse the `url: "..."` pattern inside a `<script>` tag to extract the actual spec URL.

```bash
# Save the spec to a fixed, shared path — every later step in this file (openapi-to-k6, the scenario
# generator) reads from this exact path, so there is only one file location to keep in sync.
mkdir -p /tmp/harness-perf
SPEC_PATH="/tmp/harness-perf/openapi_spec.json"
SPEC_URL=""
for path in /openapi.json /v3/api-docs /swagger/v1/swagger.json /swagger.json /api-docs; do
  if curl -sf "${BASE_URL}${path}" -o "$SPEC_PATH"; then
    SPEC_URL="${BASE_URL}${path}"
    echo "spec found: ${SPEC_URL} -> ${SPEC_PATH}"
    break
  fi
done
if [ -z "$SPEC_URL" ]; then
  echo "OpenAPI spec not found — check server is running and spec endpoint is enabled"
  exit 1
fi
```

### 1.3 $ref Dereference

A spec containing `$ref` may need to be resolved before tools can process it.

| Tool | License | Purpose | Source |
|---|---|---|---|
| prance | MIT | Python — $ref resolve + validation | https://github.com/RonnyPfannschmidt/prance |
| schemathesis | MIT | $ref resolve + contract testing | https://github.com/schemathesis/schemathesis |
| json-schema-faker | MIT | Generate example values (JS) | https://github.com/json-schema-faker/json-schema-faker |

### 1.4 Example-Value Override Rules

Per the OpenAPI 3.1.1 spec:

- Field-level `example` (singular) → a single example value.
- Field-level `examples` (plural) → a name-keyed map: `{ value, summary }`.
- For load testing, prefer the first entry of `examples` (or the `default` key).
- The example of a `$ref`-referenced schema can be overridden after resolving the reference.

Source: https://spec.openapis.org/oas/v3.1.1.html · 3.0→3.1 upgrade: https://learn.openapis.org/upgrading/v3.0-to-v3.1.html

---

## 2. Load Tools

### 2.1 First choice: openapi-to-k6 + k6 (AGPL-3.0)

> **License note**: openapi-to-k6 and k6 are both **AGPL-3.0**.
> - **Internal CI / development use**: harmless. AGPL imposes no source-disclosure obligation for internal use.
> - **When to avoid**: when redistributing the tool itself or hosting it as a SaaS.
> For ordinary internal team performance checks, using an AGPL-3.0 tool is fine.

| Tool | Version check | Source |
|---|---|---|
| openapi-to-k6 | `npx @grafana/openapi-to-k6 --version` | https://github.com/grafana/openapi-to-k6 |
| k6 | `k6 version` (need **v0.57+** for native TypeScript — see note below) | https://grafana.com/docs/k6/latest/ |

**Installation (if missing):**
```bash
# openapi-to-k6 (usable immediately via npx; the bare package name alone is NOT resolvable —
# always pass the scoped package @grafana/openapi-to-k6)
npm install -g @grafana/openapi-to-k6  # or use npx directly

# k6 (per OS)
# macOS: brew install k6
# Linux: https://grafana.com/docs/k6/latest/set-up/install-k6/
# Windows: choco install k6  or the official MSI
```

> **k6 + TypeScript**: openapi-to-k6 generates a **TypeScript** client (`.ts`), and k6 **v0.57+** runs
> `.ts` files natively (transpiles via esbuild at runtime; type-stripping only, no type-checking). On an
> older k6, either upgrade or pre-compile the generated file to `.js` yourself (e.g. `tsc`/`esbuild`) before
> importing it. Source: https://grafana.com/docs/k6/latest/using-k6/javascript-typescript-compatibility-mode/

**Running (100 times per endpoint):**

> ⚠️ `k6 run --iterations N` is the run count for the **whole script**, **not** the per-endpoint count.
> When there are multiple endpoints, a plain `--iterations 100` does **not guarantee** "100 runs per API".
> To measure **each endpoint exactly 100 times**, use k6 **scenarios** with a separate scenario
> (`iterations: 100`) per endpoint, one scenario per operation.

```bash
# 1) OpenAPI → k6 client. openapi-to-k6's CLI takes POSITIONAL args (spec, then an output DIRECTORY) —
# there is no `-o <file>` flag. It writes ONE .ts file into that directory, named after the spec's
# info.title (e.g. a spec titled "Test API" produces testAPI.ts) — not a fixed filename, so discover it.
mkdir -p /tmp/harness-perf/client
npx @grafana/openapi-to-k6 /tmp/harness-perf/openapi_spec.json /tmp/harness-perf/client --disable-analytics
CLIENT_FILE=$(find /tmp/harness-perf/client -name '*.ts' | head -1)
echo "generated client: ${CLIENT_FILE}"
```

> **Client shape**: the generated file exports a single **class** (e.g. `TestAPIClient` for a spec titled
> "Test API") — **not** top-level functions. Each spec `operationId` becomes a class **method** of the
> exact same name (verified against real `openapi-to-k6 0.4.1` output), returning `{ response, data,
> operationId }`. Instantiate the class once with `{ baseUrl }`, then call one method per operation.

> **Executor choice matters**: `shared-iterations` treats `iterations` as a TOTAL shared across all `vus`
> (exactly "100 per endpoint"). `per-vu-iterations` instead runs `iterations` **per VU**, i.e. `vus * iterations`
> total — using it here would silently run 1000 iterations per endpoint instead of the promised 100.

```typescript
// /tmp/harness-perf/k6-load.ts — per-endpoint scenarios (100 TOTAL iterations each, shared across 10 VUs)
// Import path/class name are illustrative — see §2.1's generator below to derive them from the real
// generated file rather than hardcoding.
import { TestAPIClient } from './client/testAPI.ts';

const client = new TestAPIClient({ baseUrl: __ENV.BASE_URL });

export const options = {
  scenarios: {
    getUsers:     { executor: 'shared-iterations', vus: 10, iterations: 100, exec: 'getUsers' },
    createOrder:  { executor: 'shared-iterations', vus: 10, iterations: 100, exec: 'createOrder' },
  },
};
export function getUsers()    { client.getUsers(); }
export function createOrder() { client.createOrder(); }
```

```bash
# 2) Run + JSON result (100 times per endpoint)
k6 run --out json=/tmp/harness-perf/k6-result.json /tmp/harness-perf/k6-load.ts
```

**Generating scenarios for an arbitrary number of endpoints:**

The two-scenario example above is illustrative. For any real spec, generate `k6-load.ts` programmatically:
find the generated class's name, confirm each spec `operationId` is really implemented as a method (by
searching for its `operationId: "..."` return-literal — more robust than assuming a naming convention,
since the method name and the string literal are both derived from the same `operationId` and must agree),
then emit one scenario + wrapper function per operation:

```javascript
// /tmp/harness-perf/gen-k6-scenarios.mjs
// Usage: node gen-k6-scenarios.mjs <spec.json> <generated-client.ts> <output k6-load.ts>
import fs from 'fs';
import path from 'path';

const [specPath, clientPath, outPath] = process.argv.slice(2);
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));

const operationIds = [];
for (const methods of Object.values(spec.paths || {})) {
  for (const [method, op] of Object.entries(methods)) {
    if (!['get', 'post', 'put', 'patch', 'delete'].includes(method)) continue;
    if (!op.operationId) {
      throw new Error(`${method.toUpperCase()} operation with no operationId — openapi-to-k6 requires one per operation`);
    }
    operationIds.push(op.operationId);
  }
}

const clientSrc = fs.readFileSync(clientPath, 'utf8');
const classMatch = clientSrc.match(/export\s+class\s+(\w+)/);
if (!classMatch) {
  console.error(`Could not find an exported class in ${clientPath} — openapi-to-k6's output shape may have changed; inspect the file manually.`);
  process.exit(1);
}
const className = classMatch[1];

const missing = operationIds.filter((id) => !clientSrc.includes(`operationId: "${id}"`));
if (missing.length > 0) {
  console.error(
    `Spec operationIds not found as methods in ${clientPath}: ${missing.join(', ')} — ` +
    `verify openapi-to-k6's output manually before generating scenarios.`
  );
  process.exit(1);
}

const scenarios = {};
operationIds.forEach((id) => {
  // shared-iterations: `iterations` is the TOTAL shared across all `vus` (exactly "100 per endpoint").
  // per-vu-iterations would instead run 100 PER VU = vus*iterations total — do not use it here.
  scenarios[id] = { executor: 'shared-iterations', vus: 10, iterations: 100, exec: id };
});

const clientRelPath = './' + path.basename(clientPath);
const out = `import { ${className} } from '${clientRelPath}';

const client = new ${className}({ baseUrl: __ENV.BASE_URL });

export const options = {
  scenarios: ${JSON.stringify(scenarios, null, 2)},
};
${operationIds.map((id) => `export function ${id}() { client.${id}(); }`).join('\n')}
`;
fs.writeFileSync(outPath, out);
console.log(`Generated ${operationIds.length} scenarios -> ${outPath}`);
```

```bash
node /tmp/harness-perf/gen-k6-scenarios.mjs /tmp/harness-perf/openapi_spec.json "${CLIENT_FILE}" /tmp/harness-perf/k6-load.ts
k6 run --out json=/tmp/harness-perf/k6-result.json /tmp/harness-perf/k6-load.ts
```

### 2.2 MIT Fallback (when avoiding AGPL)

| Tool | License | Notes | Source |
|---|---|---|---|
| oha | MIT | Rust implementation, JSON output support (`-j`), schema-like metrics | https://github.com/hatoo/oha |
| autocannon | MIT | Node.js, JSON output, p99 support | https://github.com/mcollina/autocannon |
| vegeta | MIT | Multiple endpoints via a targets file, JSON report | https://github.com/tsenart/vegeta |

**oha example (iterating endpoints directly):**
```bash
# 100 times per endpoint
oha -n 100 -c 10 -j http://localhost:8000/users > /tmp/oha-users.json
oha -n 100 -c 10 -j http://localhost:8000/orders > /tmp/oha-orders.json
```

**vegeta example (targets file):**
```bash
# targets.txt
echo "GET http://localhost:8000/users" >> targets.txt
echo "GET http://localhost:8000/orders" >> targets.txt

vegeta attack -targets=targets.txt -rate=10 -duration=10s \
  | vegeta encode --to=json \
  | vegeta report --type=json > /tmp/vegeta-result.json
```

### 2.3 For reference: simple single-URL tools (no p99 support, etc. — not recommended)

| Tool | License | Limitation | Source |
|---|---|---|---|
| hey | Apache-2.0 | CSV output only, no p99 | https://github.com/rakyll/hey |
| wrk | Apache-2.0 | No p95, requires a Lua script | https://github.com/wg/wrk |
| ab (Apache Bench) | Apache-2.0 | Single URL, limited statistics | https://httpd.apache.org/docs/2.4/programs/ab.html |

---

## 3. Report Standard

### 3.1 Required Metrics (no mean alone)

> **Principle**: the mean/avg hides the long tail. Always report the percentile distribution as well.
> Percentiles are not averaged (non-additive) — since percentiles differ by aggregation level,
> compute them only at the individual-request level.
>
> Source: https://orangematter.solarwinds.com/2016/11/18/why-percentiles-dont-work-the-way-you-think/

| Metric | Description | Required |
|---|---|---|
| p50 (median) | Half of requests are at or below this | ✓ |
| p95 | 95% of requests are at or below this | ✓ |
| p99 | 99% of requests are at or below this | ✓ |
| p99.9 | 99.9% of requests are at or below this (captures the long tail) | Recommended |
| throughput (RPS) | Requests processed per second | ✓ |
| VU (concurrency) | Number of concurrent virtual users | ✓ |
| error rate | Ratio of 5xx / connection failures (%) | ✓ |
| **PASS/FAIL against SLO** | Verdict compared to the predefined SLO | ✓ |

SLO reference: https://sre.google/sre-book/service-level-objectives/

### 3.2 Four Golden Signals Skeleton

Source: https://sre.google/sre-book/monitoring-distributed-systems/

```
### Golden Signals Summary
- **Latency**: p50 / p95 / p99 / p99.9 — PASS/FAIL against the SLO
- **Traffic**: RPS, VU, load model (constant/ramp-up/spike)
- **Errors**: error rate %, error types (5xx/4xx/timeout)
- **Saturation**: record CPU/memory when measurable (optional)
```

### 3.3 Measurement Metadata (required to record)

```
Measurement metadata:
- Tool / version: openapi-to-k6 x.y.z + k6 0.52.x
- Confirmed BASE_URL: <value> (source: flow-config / docker-compose / .env / framework-default / user-provided)
- Load model: constant / ramp-up / spike
- Duration: Xs (or iterations=100 per endpoint)
- VU (concurrency): N
- Warm-up excluded: state whether the first M runs are excluded
- CO (Coordinated Omission) correction: state applied / not applied
- Environment: local / CI / with or without network overhead
```

### 3.4 Statistical Conventions

#### Excluding Warm-up

JVM/JIT/connection-pool initialization makes the first requests slow. Remove the warm-up window from the results.
Source: https://www.azul.com/blog/ramps-in-performance-tests-best-practices/

#### Coordinated Omission (CO) Correction

If the client does not send the next request while awaiting a response, slow responses are hidden.
Using a tool capable of HdrHistogram-based CO correction (certain k6 settings, vegeta) measures the actual
latency distribution more accurately. Always state in the metadata whether correction was applied.
Source: https://github.com/HdrHistogram/HdrHistogram

The Tail at Scale reference (importance of high percentiles): https://cacm.acm.org/research/the-tail-at-scale/

#### Percentile Non-Additivity

Service A's p99 + Service B's p99 ≠ overall p99. Aggregate directly from request-level data.
Source: https://orangematter.solarwinds.com/2016/11/18/why-percentiles-dont-work-the-way-you-think/

### 3.5 Report Template

```markdown
## API Load Test Results — <date>

**Measurement metadata**
- Tool: openapi-to-k6 <version> + k6 <version>
- Load model: constant / iterations=100 per endpoint
- VU: 10 / warm-up: first 10 runs excluded / CO correction: not applied
- Environment: local (server: localhost:8000)

**SLO criteria**
| Endpoint | p99 SLO | Error-rate SLO |
|---|---|---|
| All | ≤ 500ms | ≤ 1% |

**Results**
| Endpoint | p50 | p95 | p99 | p99.9 | RPS | VU | Error rate | SLO verdict |
|---|---|---|---|---|---|---|---|---|
| GET /users | 12ms | 45ms | 120ms | 350ms | 850 | 10 | 0.0% | PASS |
| POST /orders | 80ms | 350ms | 890ms | 2100ms | 210 | 10 | 1.2% | FAIL |

**Golden Signals**
- Latency: POST /orders p99 890ms > SLO 500ms ← **note**
- Traffic: RPS 850 (GET) / 210 (POST)
- Errors: POST /orders 1.2% error rate > SLO 1%
- Saturation: not measured

**Recommendations**
- POST /orders: p99 exceeded — check the query plan and consider adding a DB index
- POST /orders: error rate exceeded — check the 5xx logs
```

---

## 4. License Summary

| Tool | License | Internal CI use | Redistribution/SaaS |
|---|---|---|---|
| openapi-to-k6 | AGPL-3.0 | Harmless | Avoid |
| k6 | AGPL-3.0 | Harmless | Avoid |
| oha | MIT | Harmless | Harmless |
| autocannon | MIT | Harmless | Harmless |
| vegeta | MIT | Harmless | Harmless |
| prance | MIT | Harmless | Harmless |
| schemathesis | MIT | Harmless | Harmless |
| json-schema-faker | MIT | Harmless | Harmless |
| hey | Apache-2.0 | Harmless | Harmless |
| wrk | Apache-2.0 | Harmless | Harmless |
| ab | Apache-2.0 | Harmless | Harmless |
