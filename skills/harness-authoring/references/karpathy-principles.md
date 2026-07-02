# Karpathy CLAUDE.md 원칙 (주입 블록)

> 구현 시 실제 원전을 fetch해 최신 문구로 갱신할 것(추측 금지). 원전: Forrest Chang의
> `andrej-karpathy-skills`(Karpathy의 LLM 코딩 관찰 distill). 아래는 검증된 4원칙 요지.

1. **Think Before Coding** — 가정을 명시하고, 모호하면 추측하지 말고 질문한다.
   복수 해석이 가능하면 임의로 고르지 말고 제시한다. 더 단순한 길이 있으면 반박한다.
2. **Simplicity First** — 요청한 것만, 최소 코드로. 요청 안 한 추상화·기능·설정·
   과방어 코드 금지. 50줄로 될 일을 200줄로 쓰지 않는다.
3. **Surgical Changes** — 변경된 모든 줄이 요청에 직결되어야 한다. 건드릴 것만
   건드리고, 내가 만든 것만 정리한다.
4. **Goal-Driven Execution** — 명령을 검증 가능한 성공기준으로 바꾼다. 다단계 작업은
   검증 체크포인트가 있는 짧은 계획을 먼저 세운다.
