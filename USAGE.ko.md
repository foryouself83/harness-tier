# harness-tier 사용 설명서

[English](USAGE.md) · **한국어**

[README](README.ko.md) 가 "핵심 생각 + 설치"라면, 이 안내는 주제별 상세 — 설정, 스킬 동작,
문제 해결, 갱신·제거를 다룸. 아래 각 주제는 영문 페이지와 한국어 쌍둥이 문서가
[`docs/usage/`](docs/usage/) 아래 짝을 이루며, `doc-sync` 가 둘을 맞춰 둠. (플러그인이
*어떻게* 동작하는지는 개발자용 [CLAUDE.md](CLAUDE.md) 참고.)

| 주제 | 다루는 내용 |
|------|-------------|
| [시작하기](docs/usage/getting-started.ko.md) | 설치 순서, 호스트 저장소에 생기는 것 |
| [설정](docs/usage/configuration.ko.md) | `flow-config.yaml` 의 모든 키, `flow-tiers.yaml` 을 편집하지 않는 이유 |
| [등급과 게이트](docs/usage/tiers-and-gates.ko.md) | 네 등급, 게이트별 검사 내용, 머지 전략, 증거 |
| [일상 작업](docs/usage/daily-work.ko.md) | `/flow` · `/commit` · `/doc-sync` · `/prose-review` |
| [승격과 릴리스](docs/usage/promotion-and-release.ko.md) | `/release-commit`, PR 모드와 브랜치 룰셋, 릴리스 토큰 |
| [배포](docs/usage/deployments.ko.md) | `/harness-deployments` |
| [CI 워크플로](docs/usage/ci-workflows.ko.md) | `/flow-init` 이 렌더링하는 워크플로 전체와 각각의 스위치 |
| [프로젝트 하네스](docs/usage/project-harness.ko.md) | `/harness-init`(언어표 포함) · `/wiki-init` · `harness-insight` |
| [수동 검증](docs/usage/manual-verification.ko.md) | `/integration` · `/performance` · `playwright-scaffold` |
| [Teams](docs/usage/teams.ko.md) | 웹훅 설정, 채널별 발송 시점 |
| [문제 해결](docs/usage/troubleshooting.ko.md) | 차단 메시지별 의미, 게이트 무반응 |
| [갱신과 제거](docs/usage/update-and-removal.ko.md) | `/flow-init` 재실행, `/flow-uninstall`, 수동 정리 |

## 라이선스

Apache License 2.0 — [LICENSE](LICENSE) 참고.
