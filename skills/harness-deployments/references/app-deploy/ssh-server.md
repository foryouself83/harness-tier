# App Deploy — SSH Server (저작 레시피)

> 이 파일은 **정적 템플릿이 아니다.** `github/deploy.*.workflow.example.yml`처럼 플레이스홀더를 치환하는 렌더 대상이
> 아니라, `/harness-deployments`가 감지된 값(호스트/포트/배포 경로/서비스명)을 직접 채워 넣어
> `.github/workflows/deploy-<name>.yml`을 **저작**할 때 따라야 하는 스켈레톤 + 결정 포인트다.

## 공식 액션 / 방식 (택1)

| 방식 | 액션/도구 | 언제 |
|---|---|---|
| A. 원격에서 빌드+배포 스크립트 실행 | `appleboy/ssh-action@v1` | 서버에 CI와 동일한 툴체인(git/런타임)이 있고, 원격에서 `git pull && build && restart` 흐름이 간단할 때 |
| B. CI에서 빌드 후 아티팩트만 전송 | rsync-over-ssh(`webfactory/ssh-agent@v0.9` + 네이티브 `rsync`) | 빌드는 GitHub 러너에서 끝내고, 서버엔 실행에 필요한 산출물만 얹고 싶을 때(서버 툴체인 최소화, 더 빠르고 재현 가능) |

**권장**: 가능하면 B(빌드는 CI, 서버는 순수 배포 대상)로 — 서버 의존성이 줄고 실패 지점이 CI 로그에 집중된다.

## 시크릿
| 시크릿 | 용도 |
|---|---|
| `SSH_HOST` | 배포 대상 서버 호스트/IP |
| `SSH_USER` | 접속 계정 |
| `SSH_KEY` | 배포 전용 SSH 개인키(PEM, `-----BEGIN ... PRIVATE KEY-----` 전체) — 서버 배포 계정 전용으로 발급, 사람 계정 키 재사용 금지 |
| `SSH_PORT` (선택) | 기본 22가 아니면 |

## 워크플로우 스켈레톤 (방식 B — rsync-over-ssh)

```yaml
name: deploy-<name>

on:
  workflow_call:
    inputs:
      tag:
        required: true
        type: string
  workflow_dispatch:
    inputs:
      tag:
        description: "배포할 태그 (예: v1.2.3)"
        required: true
        type: string

concurrency:
  group: deploy-<name>-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 15           # flow-config.deploy.timeout_minutes 로 치환
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.tag }}
          fetch-depth: 0
      - name: Build
        run: <build command>       # 스택별 빌드 명령
      - uses: webfactory/ssh-agent@v0.9
        with:
          ssh-private-key: ${{ secrets.SSH_KEY }}
      - name: Deploy via rsync
        run: |
          mkdir -p ~/.ssh && ssh-keyscan -H "${{ secrets.SSH_HOST }}" >> ~/.ssh/known_hosts
          RELEASE=releases/$(date +%Y%m%d%H%M%S)
          rsync -az --delete ./dist/ "${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }}:/srv/app/$RELEASE/"
          ssh "${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }}" "ln -sfn /srv/app/$RELEASE /srv/app/current && systemctl restart app"
```

컴포넌트는 오케스트레이터 `deploy.yml`이 `uses:`로 호출한다(`on: workflow_call` — `inputs.tag`는
release.yml이 해석한 실제 태그, 자기 해석 안 함). `workflow_dispatch`는 단독 수동 실행용.

## 결정 포인트 (스킬이 질문/판단할 것)
- 원격 실행형(A)인지 아티팩트 전송형(B)인지.
- 배포 경로/서비스 재시작 명령(systemd `restart`, pm2 `reload`, docker `compose up -d` 등) — 감지 불가하면 사용자에게 확인.
- 포트/known_hosts 처리(고정 IP면 `ssh-keyscan`으로 CI에서 매번 채우는 게 안전 — known_hosts를 시크릿으로 박아두면 서버 키 로테이션 시 깨짐).

## 무중단 배포 노트
- **릴리스 디렉터리 + symlink 스왑** 패턴을 기본값으로 삼는다: `releases/<timestamp>/`에 새 버전을 통째로 올린 뒤 `current` 심볼릭 링크를 원자적으로(`ln -sfn`) 갈아치운다 — 서비스 중단 없이 즉시 전환되고, 이전 릴리스 디렉터리가 남아있어 롤백이 `ln -sfn releases/<prev> current`로 즉시 가능하다.
- 서비스 프로세스에 직접 `git pull`을 실행해 파일을 덮어쓰는 방식은 피한다(요청 처리 중 파일이 바뀌어 부분 실패를 유발할 수 있다).
- 여러 대의 서버(로드밸런서 뒤)라면 한 대씩 순차 배포(rolling) + 헬스체크 후 다음 대상으로 진행하는 것을 고려.

## SSOT
| 항목 | URL |
|---|---|
| appleboy/ssh-action | https://github.com/appleboy/ssh-action |
| webfactory/ssh-agent | https://github.com/webfactory/ssh-agent |
