# 프로젝트 하네스

[English](project-harness.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

## `/harness-init` — 프로젝트 하네스 생성

```text
/harness-init     # 인자 없음 — 대화형 마법사
```

프로젝트에 맞는 `CLAUDE.md`·`.claude/rules/`·기술 문서를 생성함 — `/flow-init`(거버넌스
배선)과는 별개의 독립 명령. 이미 잘 갖춰진 `CLAUDE.md` 가 있을 때만 건너뜀; 건너뛰면
`/flow-init` 이 `modules[].checks` 초안을 뽑을 `docs/code-style/` 도 없고,
`/commit`·`/integration`·`/performance` 가 읽는 `docs/operations/commit-versioning-guide.md`
와 `docs/verification/*.md` 도 생기지 않음.

1. **인터뷰** — 리서치 전에 범위를 고정해 이후 단계가 추측하지 않게 함:
   - SRS 를 생성할 때는 애매하거나 빈 요구사항을 `AskUserQuestion` 으로 전부 확인함 —
     그린필드와 브라운필드 모두(브라운필드도 스켈레톤만 받고, 확정되지 않은 슬롯은
     "확인 필요"로 표시됨);
   - 감지 여부와 무관하게 주 개발 언어를 항상 확인하고, 레이어(프론트엔드/백엔드/기타)가
     다르면 레이어별로 매핑;
   - 감지된 프레임워크와 버전을 확인;
   - 생성할 산출물 — CLAUDE.md, rules, skills, agents, 기술 문서 — 를 선택하게 함, 기본
     세트는 없음;
   - 보안 스캐너, CI, 실제 폴더 스캐폴딩, 버전 고정을 항목별로 물음.
2. **리서치** — 병렬 서브에이전트(`harness-researcher` 는 웹 관행과 무료 대안, 브라운필드면
   `harness-code-analyzer` 도 실제 관행)가 각 의존성의 최신 버전이 아니라 함께 부팅되는
   스택으로 수렴함.
3. **생성** — 선택한 산출물을 분류된 폴더에 만들고, 이유를 담은 `rationale.md` 도 씀. 증거
   — `plan.json`, `manifest.json`, `critic-report.json`, `rationale.md` — 는 감사·재실행용으로
   `.claude/harness-tier/.harness/`(gitignore) 에 씀.
4. **비평** — `harness-critic` 이 품질, 파일 간 일관성, 버전 호환성을 점검하고 다듬음.
5. **미리보기 후 확인** — 만들 것을 먼저 보여주고, 확인 후에만 씀.
6. **정리** — 문서에 합쳐진 리서치 사본을 지우되 증거 메타데이터는 보존함. 문서가 아직
   참조 중인 사본은 지우지 않고 보고함 — 깨진 링크를 남기지 않기 위함.

- **덮어쓰지 않음** — 기존 파일은 관리 블록만 갱신되고, 충돌은 보고됨; 브라운필드
  충돌은 항목마다 건너뛰기/덮어쓰기를 선택함.
- **`CLAUDE.md` 만이 아니라 `.claude/rules/` 도** — 프레임워크·구조 관행은 자동 로드되는
  `.claude/rules/<name>.md` 로 만들어지고, 각각 매칭 파일에서만 로드하는 `paths` 글롭을
  가질 수 있음. `/doc-sync` 가 코드 변화에 맞춰 이를 유지함.
- **슬래시 명령은 생성하지 않음.**
- **커밋하지 않음** — [`/flow`](daily-work.ko.md#flow--일상-작업-라우터) 로 커밋함. 이번
  실행이 `docs/srs/` 를 만들었다면 이후 `/flow-init` 을 다시 돌려 `srs-verify.yml` 제안을
  받음.

### 자동 감지 언어와 프레임워크

Step 1 은 매니페스트 파일로 스택을 지문 인식함.

| 언어 | 매니페스트 | 자동 감지 프레임워크/라이브러리 |
|------|-----------|----------------------------------|
| Python | `pyproject.toml` · `requirements.txt` | FastAPI · Django · Flask |
| JavaScript / TypeScript | `package.json` | Next.js · React · Vue · Nuxt · Svelte · Angular · Express · NestJS |
| Go | `go.mod` | (모듈 단위) |
| Java | `pom.xml` · `build.gradle[.kts]` | Spring Boot · Spring · Quarkus · Micronaut · Ktor |
| Kotlin | `build.gradle.kts` · `pom.xml` | 위 JVM 표와 공유 |
| C# | `*.csproj` | ASP.NET Core · Blazor WASM · Razor · WPF · WinForms · MAUI · EF Core |
| C++ | `CMakeLists.txt` · `vcpkg.json` · `conanfile.*` | CMake · Boost · Qt · OpenCV · GoogleTest · Catch2 · fmt · spdlog |
| Rust | `Cargo.toml` | actix-web · axum · Rocket · warp · tokio |
| PHP | `composer.json` | Laravel · Symfony · Slim · CodeIgniter |
| Ruby | `Gemfile` | Rails · Sinatra · Hanami |
| Swift | `Package.swift` · `*.xcodeproj`/`*.xcworkspace` | Vapor · SwiftNIO · Alamofire · RxSwift |
| Scala | `build.sbt` | Play · Akka · Akka HTTP · http4s · Cats Effect |

이 표 밖의 스택도 하네스를 받음 — 그린필드/브라운필드 판정은 소스 파일 확장자로,
`harness-researcher` 는 어떤 프레임워크든 관행을 조사함; 결정론적 지문 인식만 위 항목에
한정됨.

## `/wiki-init` — 문서를 지식 그래프로

```text
/wiki-init   # 인자 없음 — 대화형; disable-model-invocation, 직접 호출
```

**선행조건**: `.claude/harness-tier/config/flow-config.yaml` 이 있어야 함. 없으면 먼저
`/flow-init` 을 실행함.

기존 문서를 개념 하나-파일 하나로 YAML front matter 와 함께 이관하고(임베딩 없음),
`docs/graph/graph.yaml` 을 생성함. 관계는 직접 쓰는 front matter이고 기계적으로 그래프에
읽힘; 원본은 지우지 않고 연결만 함. 이미 `wiki_id` 가 있는 문서는 다시 묻지 않는
멱등적 동작.

`flow-config.wiki.enable: true` 를 설정하고 `wiki_graph.py --build` 다음 `--verify` 를
돌리는 것으로 끝남. 같은 세션에서 verify 가 통과하지 않으면, 아무도 고치지 않은 그래프로
저장소의 모든 커밋을 막는 대신 `enable` 을 다시 `false` 로 되돌린 뒤 끝냄. verify 가
통과하면 `wiki-verify.yml`([CI 워크플로](ci-workflows.ko.md)) 을 제안함 — 거절하면 Claude
세션 밖에서 생기는 그래프 드리프트를 아무것도 잡지 못한 채 남김.

빌드된 뒤로는 [`/doc-sync`](daily-work.ko.md#doc-sync--문서를-맞춰-둠) 가 그래프와 각 노드의
`sources` 스탬프를 맞추고, [`wiki` 게이트](tiers-and-gates.ko.md#wiki) 가 그 동기화를 매
커밋마다 읽기 전용으로 검증함. 그래프는 개발 시 읽는 경로이기도 함:
[`/flow`](daily-work.ko.md#flow--일상-작업-라우터) 의 Dev 트랙은 계획을 세우기 전에 바뀔
파일을 그것을 문서화하는 노드로 매핑함.

## `harness-insight` — 활동과 메모리 리뷰

```text
/harness-insight [period]   # 예: 7 days · 2 weeks · 30 days · today (기본 7 days)
```

기간에 대한 Claude Code 트랜스크립트 — 보낸 프롬프트와 도구 사용 — 를 집계해 대화에
리포트를 출력함: 작업 분포, 하네스 규칙으로 만들 만한 반복 지시, 활동 핫스팟, 다음
행동. 이어서 누적된 프로젝트 메모리를 리뷰해 삭제나 `.claude/rules`/`docs/` 로의 승격을
제안하고, 사용자가 승인해야만 적용함. 리포트 파일은 만들지 않음 — 리포트 출력 뒤
중간 파일을 지움. Claude Code 가 작업한 적 없는 cwd 는 추측 대신 메시지로 멈춤.
