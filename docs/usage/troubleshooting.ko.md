# 문제 해결

[English](troubleshooting.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

게이트 메시지는 한국어로 출력되며, 아래 각 제목은 그 메시지의 시작을 인용함. 여기서
설명하는 모든 차단은 2층 — Claude 세션의 커밋이나 머지
([게이트가 보는 것](tiers-and-gates.ko.md#게이트가-보는-것)) — 에서 일어남.

## 막혀요 — "python3 / PyYAML 필요"

메시지: `게이트에 python3 가 필요합니다` · `게이트에 python 3.8+ 가 필요합니다` ·
`게이트에 PyYAML 이 필요합니다`.

프로젝트 언어와 무관하게 게이트는 `python3` 3.8 이상과 PyYAML 이 필요함. 없으면
검사가 조용히 빠지는 대신 모든 커밋을 막음.

```bash
python3 -m pip install pyyaml                       # 훅이 부르는 그 python3 에
bash .claude/harness-tier/scripts/check-deps.sh    # 무엇이 빠졌는지 나열
```

`uv add` 는 훅이 못 볼 수 있는 venv 에 설치되므로 `python3 -m pip` 를 씀.

## 미분류 커밋으로 막혀요

메시지: `flow 미진입: 분류되지 않은 커밋입니다.`

현재 브랜치에 `tier` 마커가 없어 `/flow` 를 거치지 않은 것으로 보임. `/flow <작업>` 을
실행하면 작업을 분류하고 마커를 씀. `/commit` 만으로는 분류되지 않음. 강제가 필요 없는
저장소는 [`/flow-uninstall`](update-and-removal.ko.md#flow-uninstall--호스트-배선-제거) 로
게이트를 제거함.

## 막혀요 — 증거 없음

메시지: `flow 게이트: '<tier>' 티어는 [...] 증거가 필요합니다.` 또는, 승격 브랜치에서
`<tier> 게이트 (브랜치 '<branch>'): [...] 증거가 필요합니다.`

나열된 게이트에 `.done` 마커가 없음. 아예 돌지 않았거나 편집이 그것을 무효화한
것 — 그때는 `this edit voided the review, doc-sync gate evidence` 라고 세션에 알림.
나열된 게이트를 `/flow`(Docs, Dev)나 `/release-commit`(Staging, Release)으로 다시
돌림. 자세한 내용은 [게이트 증거](tiers-and-gates.ko.md#게이트-증거) 참고.

## 막혀요 — 머지 전략

메시지: `머지 전략 위반 — '<source>' → '<target>' 는 <flag> 가 필요합니다.` 또는
`… 에는 <flag> 를 쓰지 않습니다.`

`git merge` 의 플래그가 그 브랜치 흐름의 규칙을 어김. 메시지가 말하는 플래그를 씀 —
표는 [머지 전략](tiers-and-gates.ko.md#머지-전략) 참고. `[경고] 머지 전략: … rebase
선행이 요구됩니다` 는 경고일 뿐임 — feature 브랜치를 먼저 rebase 하거나, `origin`
참조가 낡았다면 무시함.

## 막혀요 — 모듈 사전검사 실패

메시지: `모듈 사전검사 실패: <command>.`

`modules[].checks` 명령이 0 이 아닌 코드로 끝남. 출력은 메시지 위에 인쇄됨. 원인을
고치고 다시 커밋함. 함께 따라올 수 있는 것: 어느 모듈에도 안 걸린 파일
(`모듈 미커버라 사전검사 생략`) — 새 모듈이면 등록함, 그리고 알 수 없는 `when` 값은
`every-commit` 으로 읽힘([`modules` 와 `checks`](configuration.ko.md#modules-와-checks)).

## 막혀요 — wiki 게이트

위키 그래프와 문서가 어긋나거나, 노드가 `sources` 스탬프만 바뀜. 
`python3 .claude/harness-tier/scripts/wiki_graph.py --build` 로 재빌드하고
`docs/graph/graph.yaml` 을 문서와 함께 스테이징한 뒤 다시 커밋함. 무엇이 위반인지는
[`wiki`](tiers-and-gates.ko.md#wiki) 참고.

## `git commit` 을 언급만 했는데 차단돼요

그러면 안 됨. 게이트는 셸이 읽는 방식으로 명령을 읽고 딱 하나만 물음: 진짜
`git … commit` 이 있는가. 따옴표 안, 주석, heredoc 본문 속 언급은 텍스트일 뿐이라
`grep "git commit"` 과 `git log --oneline && echo "now commit"` 모두 그대로 실행됨.

의도적으로 걸리는 형태 하나: commit 모양의 텍스트를 따옴표로 감싸 실행하는데,
게이트가 그 프로그램을 읽는 도구로 알지 못하는 경우. 검색·목록 도구는 알려져 있음 —
`grep`, `rg`, `ls`, `cat`, `head` 와 그 부류는 그대로 실행됨. `awk`, `sed`, `find`,
`ack`, `ag` 는 아님 — 각자 자기 인자 안에 적힌 명령을 실행할 수 있고, `git` 자신도
아니라서 `git log --grep="git commit"` 도 걸림. `less` 도 그 부류에 없음 — 대부분
배포판의 로그인 프로필이 설정하는 `LESSOPEN` 은 실행할 명령을 이름으로 담음. `more`
도 같은 프로그램인 경우가 많아 함께 걸림. 그래서 `grep 'git commit' f | less` 는
거부되고 `grep 'git commit' f` 는 아님.

따옴표를 걷어냈을 때 `git` 과 서브커맨드가 온전한 두 단어로 서 있는지가 기준이라,
`awk '/git commit/{print}'` 는 통과함 — 단어 뒤의 `/` 가 끊음 — 반면
`sed -e 's|git commit|Y|g'` 는 아님. 같은 명령 안 어디든 `$( … )`, 백틱, `$(( … ))`
이 있으면 이 예외를 거둬들임 — 치환이 출력하는 것 자체가 명령이기 때문; 별도
명령으로 떼어내면 읽는 도구들이 다시 알려짐. 그 앞에 붙은 환경변수 대입
(`LC_ALL=C grep …`) 도 마찬가지 — 프로그램 안쪽에 손대는 것이고, 이게 `LESSOPEN`
이 `less` 로 하여금 아무도 쓰지 않은 명령을 실행하게 만드는 방식과 같음.

따옴표가 다른 명령의 것이면 `;`, `&&`, 줄바꿈으로 둘을 나누는 것으로 충분함 — 명령
목록의 각 부분은 따로 읽힘. 그 명령 자신의 인자라면 나눌 것이 없고, 그때의 거부는
미분류 커밋이 받는 것과 같음: `/flow` 로 작업을 분류하면 그 등급의 증거가 생긴
뒤에는 그 명령도 실행됨.

다른 문제로 막힌다면 거부 메시지를 읽음. python3 가 없으면 게이트는 언급과 실행을
구분할 수 없어 추측 대신 차단하고, 설치를 안내함. 그 외라면 호스트의 게이트 스크립트
사본이 플러그인보다 오래된 것 — `/flow-init` 을 다시 돌림.

## `/flow` 가 Dev 작업에서 멈춰요

`superpowers@claude-plugins-official` 플러그인이 없음. 설치한 뒤
([README 요구 의존성](../../README.ko.md#요구-의존성)) `/flow` 를 다시 실행함 — 직접
구현으로 넘어가지 않음.

## `/flow-init` 이 게이트 문제로 끝나요

커밋 게이트가 돌지 않을 실행은 완료 메시지 대신 아래 중 하나로 끝남:

| 메시지 시작 | 원인 | 해결 |
|-------------|------|------|
| `커밋 게이트가 쓰는 파일이 호스트에 없거나 손상됐습니다` | 복사된 스크립트나 정책이 없거나 플러그인과 다름 | 위 `[!]` 단계를 해결하고 `/flow-init` 재실행 |
| `settings.json 을 읽지 못해` | `.claude/settings.json` 이 파싱되지 않거나, UTF-8 이 아니거나, 객체가 아님 | 파일을 고치고 `/flow-init` 재실행 |
| `커밋 게이트가 settings.json 에 없습니다` | 훅이 없거나 변형됐거나, `Bash` 를 덮지 못하는 matcher 아래 있음 | 위 `[!]` 단계를 해결하고 `/flow-init` 재실행 |
| `settings.json 의 disableAllHooks 가 켜져 있어` | `disableAllHooks: true` 가 모든 훅을 끔 | 설정을 제거 |

## 게이트가 아무 반응이 없어요

막혀야 할 커밋이 그냥 통과함. 확인 순서:

1. **셸 도구 부족.** 게이트는 bash 이고 `timeout`, `cat`, `grep`, `sed`, `awk`, `head`
   로 명령을 읽음; 없으면 입력을 못 읽고 통과시킴. Windows 에서는 Git for Windows 를
   설치함. `bash .claude/harness-tier/scripts/check-deps.sh` 실행.
2. **훅이 등록 안 됐거나 안 걸림.** `/flow-init` 을 다시 돌려 마지막 줄을 읽음 — 없는
   파일, 없는 훅, `Bash` 를 건너뛰는 matcher, `disableAllHooks` 중 하나를 지목함.
3. **정책 파일 없음.** `flow-tiers.yaml` 없이는 게이트가 분류할 수 없어 설계상 커밋을
   통과시킴; `/flow-init` 이 복구함.
4. **다른 브랜치의 `tier` 마커.** 다른 브랜치에서 쓰인 마커는 현재 브랜치를 분류하지도
   막지도 않아 통과함; 이 브랜치에서 `/flow` 를 실행함.
5. **Claude 세션 밖에서 실행된 커밋.** 터미널·CI·GitHub 커밋은 2층에 전혀 닿지 않음.
