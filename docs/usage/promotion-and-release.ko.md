# 승격과 릴리스

[English](promotion-and-release.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

승격은 integration 을 staging 으로(릴리스 후보) 또는 staging 을 production 으로(릴리스) 옮김.
커밋이 놓이는 브랜치가 등급을 정하므로 `tier` 마커도 `/flow` 단계도 없음. 모든 단계 뒤의
규칙은 [`rules/promotion.md`](../../rules/promotion.md) 참고.

## `/release-commit` — 승격 하나를 실행

```text
/release-commit [staging | release]
```

인자가 없으면 어느 승격인지 물음. "릴리스 해" 같은 요청도 여기로 옴.

1. **릴리스 모델을 읽음.** `grep -c Release-Level .github/workflows/release.yml` 로 범프
   레벨을 강제할 수 있는지 답함. `/flow-init` 이 렌더하는 템플릿은 모두 트레일러를 읽음;
   0 은 트레일러를 읽지 않는 손으로 쓴 워크플로라는 뜻이고, 레벨 질문을 건너뜀. 두 번째
   `grep -c next-version` 은 `continue` 이전에 렌더된 워크플로를 가려냄
   ([새 템플릿 도입](#새-템플릿-도입)). `release.yml` 이 없으면 멈추고 `/flow-init` 을 안내함.
   `workflow_dispatch` 로 레벨을 받는 워크플로는 없으므로 그것을 트리거해도 아무것도
   강제되지 않음.
2. **Staging** —
   - staging 에 대기 rc 가 있으면 먼저 staging 을 integration 으로 백머지(fast-forward,
     안 되면 `--no-ff`) — **재승격**;
   - `origin/<staging>..origin/<integration>` 에 대한 독립 리뷰를 `review_checklist` 기준으로
     수행;
   - 커밋 타입과 `commit_guide` 의 0.x 정책에서 권장 레벨을 계산;
   - 레벨을 강제할 수 있는 곳에서는 항상 물음 — auto / patch / minor / major, 재승격이면
     continue / patch / minor / major — 선택지마다 그것이 만드는 버전을 라벨로 붙임
     ([릴리스 레벨](#릴리스-레벨)). `0.x` 에서 `major` 를 고르면 `1.0.0` 으로 곧장
     넘어감을 경고함;
   - 릴리스 토큰이 push 할 수 없을 때 경고(best effort, 절대 차단하지 않음);
   - `review`·`bump` 마커 기록.
3. **Release** — `origin/<staging>` 가 대기 중인 `X.Y.Z-rc.N` 버전을 갖는지 확인하고,
   `/security-review` 를 돌리고, `security` 마커를 기록함. 코드 리뷰는 없음 — Dev 와
   Staging 에서 이미 이 diff 를 읽었기 때문.
4. **머지한 뒤 커밋하고 push 함.** `git merge --no-ff --no-commit origin/<source>` 다음
   `/commit` 이 대기 중인 머지를 `Merge <source>: <headline>` 으로 쓰고, 이어서 push —
   릴리스 워크플로를 쏘는 것이 그 push 임. Staging 에서 워크플로가 트레일러를 읽으면
   `Release-Level: <choice>` 를 붙임 — `auto` 포함, 항상 명시. CI 는 `git log -1` 만
   읽으므로 순서가 중요함: 머지 전에 커밋된 트레일러는 한 커밋 뒤로 밀려나고 실행은
   `auto` 로 읽음. Staging 은 그 뒤 릴리스 상태를 다시 읽음: `pending:` 이 push 전과
   다른 rc 를 가리킬 때만 rc 가 실제로 cut 된 것이고, 그 외 결과는 승격 미완료를 뜻함.
5. **주기를 닫음.** 릴리스 뒤:
   - production → integration 백머지 — 필수임; 아니면 릴리스된 태그가 integration 에서
     도달 불가능해지고 다음 버전이 잘못 계산됨;
   - production → staging 백머지, fast-forward 전용 — 거부된 fast-forward 는 건너뛸 뿐
     `--no-ff` 로 강제하지 않음, 그러면 아무도 승격하지 않은 rc 가 하나 더 생김.

   두 승격 모두 끝나면 자신의 증거 마커를 지움. rc 에서 멈춘 실행도 포함 — `bump.done` 을
   지우는 것은 이것뿐이고, 안 지우면 다음 승격이 이를 자신의 통과 증거로 읽음.

**hotfix 릴리스도 같은 백머지를 요구함.** `/flow` 는 `hotfix/*` 브랜치를 `/release-commit` 에
넘기고, 그것이 hotfix 를 production 으로 squash 하고(`promotion` 아래서는 PR), 릴리스 CI 의
정식 태그를 기다린 뒤 위의 두 백머지를 실행함. hotfix 가 staging 에 대기 중인 rc 의 base 나
그보다 높은 버전을 출시했으면 그 rc 는 더 이상 릴리스할 수 없음: 다음 integration → staging
승격은 `patch` 이상을 골라야 함.

`wiki` 게이트가 승격 커밋을 막으면
`python3 .claude/harness-tier/scripts/wiki_graph.py --build` 로 재빌드하고 `graph.yaml`
을 그 커밋에 스테이징함.

승격은 저장소 전체를 한 버전으로 매김. 승격 머지 메시지에 CI-skip 마커를 절대 넣지 않음 —
릴리스 잡이 전혀 돌지 않고 아무도 알아채지 못함.

## 릴리스 레벨

staging 승격 커밋은 `Release-Level:` 에 `auto`·`continue`·`patch`·`minor`·`major` 중 하나를
실음. **대기 rc** 는 같은 `X.Y.Z` 의 정식 태그가 없고 최고 정식 태그보다 높은 최고
`vX.Y.Z-rc.N` 태그이며, 전체 태그 목록에서 읽음. 이후 릴리스가 뒤에 남긴 rc 는 잇지 않음 —
그것을 마무리하면 버전이 내려감.

| 선택 | 대기 rc 없음 (마지막 정식 `1.0.3`) | 대기 `1.1.0-rc.2` |
|---|---|---|
| `auto` | 릴리스 도구가 커밋에서 도출한 레벨 | 제시하지 않음 |
| `patch` | `1.0.4-rc.1` | `1.1.1-rc.1` |
| `minor` | `1.1.0-rc.1` | `1.2.0-rc.1` |
| `major` | `2.0.0-rc.1` | `2.0.0-rc.1` |
| `continue` | 제시하지 않음 | `1.1.0-rc.3`, 권장 |

재승격에서 강제 레벨은 `1.1.0` 을 정식 릴리스로 건너뜀. 주의하지 않으면 깨지는 것:

- **오타·빈 값·서로 다른 두 트레일러는 rc 실행을 실패시킴**, 대기 rc 없는 `continue` 도
  마찬가지. 도출된 범프로 떨어지는 경로는 없음.
- **gitversion·jreleaser 는 아무것도 도출하지 못함**: `auto` 는 대기 rc 를 잇고, 없으면
  `patch`.
- **python-semantic-release, 강제 레벨**: pyproject `[project]` 버전과
  `.claude-plugin/plugin.json` 만 기록함. 다른 `version_variables` / `version_toml` 대상은
  `auto` 경로에서만 움직임.
- **Node semantic-release, 강제 레벨**: rc 는 annotated 태그와 GitHub prerelease 뿐 — npm
  publish·changelog·버전 커밋 없음. 대기 중인 동안 트레일러 없는 push 는 그 rc 를 잇고,
  출시될 때까지 커밋 타입의 레벨은 무시됨. squash 승격은 릴리스 커밋에서 그 rc 를 가려,
  그 릴리스는 semantic-release 가 정함.
- **hotfix 가 rc 의 base 나 그보다 높은 버전을 먼저 출시하면 릴리스 실행이 실패함**:
  `vX.Y.Z already exists — a hotfix shipped this base` 또는
  `vX.Y.Z is below the latest release`. staging 을 `patch` 이상으로 재승격한 뒤 릴리스함.

### 새 템플릿 도입

`/flow-init` 은 이미 렌더된 `release.yml` 을 덮어쓰지 않음. `continue`·`auto` 이전에 렌더된
것은 `Release-Level: major | minor | patch` 만 읽고 finalize 가드가 없음. `/release-commit`
은 이를 가려내(`next-version` 개수 0) 경고하고, 첫 승격에서는 patch / minor / major 만
제시하며, 재승격에서는 트레일러를 쓰지 않음 — 그 워크플로가 rc 를 스스로 이어감.
`continue`·`auto`·가드를 쓰려면 `.github/workflows/release.yml` 을 지우고 `/flow-init` 을
다시 실행한 뒤 손으로 고친 부분을 옮겨 옴.

## PR 워크플로와 브랜치 룰셋

`merge_workflow.pull_request` 에 흐름이 있으면([설정](configuration.ko.md#merge_workflowpull_request))
그 흐름의 머지가 PR 이 됨. 커밋은 여전히 로컬에서 만들어지므로 gitlint 와 등급 게이트는
전과 같이 실행됨. [머지 전략](tiers-and-gates.ko.md#머지-전략) 검사는 그 흐름의 `git merge`
를 전혀 보지 못하므로, 강제가 GitHub 브랜치 룰셋의 허용 머지 방식으로 옮겨감:

| 대상 브랜치 | 허용 방식 |
|-------------|-----------|
| integration | `squash` + `rebase` |
| staging · production | `merge` 만 |

`/flow-init` 이 `gh` 로 현재 룰셋 상태를 읽어 간극을 보고함. 절대 직접 바꾸지 않음.

- **`promotion` 은 정확한 치환.** 브랜치마다 방식 하나뿐. 승격 PR 은 "Create a merge
  commit" 으로만 머지함 — rebase 는 `[skip ci]` 릴리스 커밋을 head 로 남겨 릴리스가
  전혀 돌지 않고, squash 는 릴리스 히스토리를 파괴함. 레벨 질문이 고른 트레일러를 고정함:

  ```bash
  gh pr merge "$PR" --merge --subject "Merge <staging>: release X.Y.Z" --body "Release-Level: patch"
  ```

- **`daily` 는 부분적.** 룰셋은 대상 브랜치를 겨냥하므로 `feature/*` PR 과 `fix/*` PR 을
  구분하지 못함. "integration 에 머지 커밋 없음"만 보장함. PR 을 넘길 때 방식을 말해 둠:
  `feature/*` 는 "Squash and merge", `fix/*` 는 "Rebase and merge".
- **룰셋은 그 브랜치로의 모든 머지를 다스림.** production 에서는 `hotfix/*` 도 걸리므로
  `promotion` 아래서는 hotfix 도 PR 을 거침. integration 에서는 릴리스 뒤 백머지의 push 를
  막음. staging 에서는 staging 백머지 push 를 막지만 고칠 필요는 없음 — 거부된 push 가
  그 단계의 정상적인 끝임.
- **바이패스 액터.** `promotion` 룰셋은 릴리스 자동화용 바이패스 액터가 필요함, 아니면
  릴리스 도구의 버전 범프 push 가 거부되어 릴리스가 멈춤. integration 룰셋은 백머지를
  수행하는 누군가를 위한 액터가 필요함. 둘 다 `bypass_mode: always` — `pull_request`
  액터는 직접 push 할 수 없음.

PR 모드에서는 `/flow` 와 `/release-commit` 모두 PR 이 머지된 뒤에만 증거를 지움 — PR
브랜치에 올라간 리뷰 반영 커밋도 첫 커밋과 똑같이 게이트를 받음.

## 릴리스 토큰 쓰기 권한

릴리스 워크플로가 버전 범프와 태그를 push 하므로 그 토큰은 **쓰기** 권한이 필요함.
렌더링된 모든 릴리스 템플릿은 `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}` 로
인증함: `RELEASE_TOKEN` 시크릿이 없으면 기본 `GITHUB_TOKEN` 으로 돌아감.

1. **저장소 설정** — Settings → Actions → General → **Workflow permissions** →
   **Read and write permissions** → Save.
2. **조직 제한** — 조직이 Actions 를 읽기 전용으로 캡한다면 조직 관리자가 완화하거나
   저장소가 스스로 고르게 해야 함.
3. **보호된 브랜치나 룰셋** — 릴리스 브랜치가 push 를 제한하면 Actions 봇이나 토큰
   소유자를 바이패스 목록에 추가함.
4. **`RELEASE_TOKEN`** — `GITHUB_TOKEN` 으로 부족할 때(보호 우회, 다운스트림 워크플로
   트리거) `Contents: Read and write` 를 가진 파인그레인 PAT 를 만들고, 릴리스가 워크플로
   파일을 건드리면 `Workflows: Read and write` 도 추가해, 저장소 시크릿 `RELEASE_TOKEN`
   으로 저장함. 워크플로 수정은 필요 없음.

렌더링된 워크플로에는 토큰 사전점검이 없음: 읽기 전용 토큰은 push 시점에서 실패함.
`/release-commit` 은 Staging 승격 중 `check-token-write.sh` 를 실행해 알 수 있을 때
먼저 경고함.
