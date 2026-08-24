# 배포 / 확인 방법

**배포됨: https://this-week-taste.vercel.app** (2026-08-24)

`web/`은 순수 정적 사이트다(`output: "export"`). 서버 런타임이 없어서 아무 정적 호스팅에나
올라가고, 빌드 산출물은 `web/out/` 1.1MB다.

⚠️ **이 주소는 세 곳과 묶여 있다.** 바꾸려면 셋을 함께 고쳐야 하고,
어긋나면 `tests/test_normalize.py`가 실패한다.

| 어디 | 무엇 |
|---|---|
| `web/config/site.ts` | `url` |
| `scrapers/base.py` | `DEFAULT_USER_AGENT`의 `+https://.../about` |
| `web/app/about/page.tsx` | 그 페이지가 실제로 존재해야 한다 |

---

## 1. 지금 당장 로컬에서 보기

```bash
cd web && npm run dev          # http://localhost:3000
```

가장 확실하다. 코드를 고치면 바로 반영된다.

빌드된 결과물을 그대로 보고 싶으면:

```bash
make site
cd web/out && python3 -m http.server 8000    # http://localhost:8000
```

> `trailingSlash: true`로 `week/2026-W33/index.html`을 내보내므로 어떤 정적 서버에서도
> 경로가 그대로 동작한다. 이 설정이 없으면 `week/2026-W33.html`이 되어, 확장자 없는 경로를
> `.html`로 매핑해주는 호스트(Vercel, Netlify 등)에서만 열린다.

---

## 2. 공개 배포

### 발행물이 저장소 안에 있다는 점이 핵심

**DB도, 백엔드도, 빌드 시 외부 호출도 없다.** `git push` → 호스트가 다시 빌드 → 끝이다.
사이트가 읽는 파일은 `data/weeks/<week>.json` 하나뿐이다.

⚠️ **수집 데이터는 이 저장소에 없다.** 스냅샷·원본은 비공개 데이터 저장소에 있다
([ADR-0010](adr/0010-repo-public-scope.md)). 빌드에는 필요 없으므로 호스트 설정은
영향받지 않는다 — 다만 `data/`를 통째로 있다고 가정하지 말 것.

### 호스팅 설정은 저장소 안에 있다

**UI에서 설정하지 않는다.** 루트의 `vercel.json`이 전부 지정한다.

```json
{ "framework": null,
  "installCommand": "cd web && npm ci",
  "buildCommand":   "cd web && npm run build",
  "outputDirectory": "web/out" }
```

UI 설정으로 두면 누가 언제 바꿨는지 알 수 없고, 프로젝트를 다시 만들 때마다 되풀이해야 한다.

> ⚠️ **Root Directory를 `web`으로 잡으면 안 된다.** `web/lib/weeks.ts`가
> `process.cwd()/../data/weeks`를 읽으므로 그 위 경로가 필요하다.
> 저장소 루트에서 빌드하고 `cd web` 하는 것이 이 설정의 이유다.

`.vercelignore`가 파이프라인 파일(`pipeline/`, `scrapers/`, `requirements.txt` …)을 제외한다.
빌드에 필요 없기도 하지만, `requirements.txt`가 루트에 있으면 **Vercel이 이 저장소를
파이썬 프로젝트로 감지해서** 화면에 그렇게 뜬다. 동작에는 지장이 없어도 다음 사람이 헷갈린다.

⚠️ **`data/weeks/`는 제외하면 안 된다.** 빌드 때 읽는다.

### 다른 호스트로 옮긴다면

| 항목 | 값 |
|---|---|
| Root directory | 저장소 루트 |
| Build command | `cd web && npm ci && npm run build` |
| Output directory | `web/out` |
| Node version | 20 이상 |

GitHub Pages를 쓴다면 Actions에서 `web/out`을 아티팩트로 올리면 된다. 다만 사용자 페이지가
아닌 프로젝트 페이지(`/<repo>/` 하위 경로)에 올릴 경우 `basePath` 설정이 추가로 필요하다.

### 발행된 주차가 없을 때

홈이 "아직 발행된 주차가 없습니다"를 명시적으로 보여준다(CLAUDE.md 2.4 — 조용한 빈 페이지
금지). 배포는 성공하는데 화면이 비어 있다면 `data/weeks/`에 파일이 없는 것이다.

---

## 3. 주간 자동화 (8장 5단계)

사람 손을 매주 타지 않으려면 이게 필요하다. 형태는 이렇게 된다:

### 무엇을 자동화하고 무엇을 안 하는가

**수집(snapshot → diff)만 자동으로 돌린다. 발행(enrich → curate → publish)은 사람이 돌린다.**

이유는 LLM 편집 경로다. 지금 `curate.py`를 `claude -p`(구독 인증)로 돌리고 있는데
**CI에서는 그게 안 된다** — 바이너리도 없고 구독 인증도 못 쓴다. API 키 없이 자동 발행하면
전량이 `blurb: null`로 나간다. 발행 품질보다 발행 자체가 우선이라는 6장 원칙에 어긋나지는
않지만, 사이트가 말끔하지 않아진다.

그래서 경계를 이렇게 둔다.

```
Actions (매주 자동)     snapshot → diff        → 비공개 데이터 저장소에 커밋
사람 (주 1회, 몇 분)     enrich → curate → publish → merge → 공개 저장소에 커밋 → 호스트 재빌드
```

이 경계는 [ADR-0009](adr/0009-weekly-effort-goal.md)와 맞는다 — 자동으로 할 수 있는 수집은
자동으로 하고, 사람은 발행 결과를 보고 판단하는 자리에만 들어간다.

실제 파일은 `.github/workflows/weekly.yml`이다. 뼈대는 이렇다:

```yaml
on:
  schedule:
    - cron: "0 1 * * 1"     # 매주 월요일 KST 10:00
  workflow_dispatch:
jobs:
  collect:
    steps:
      - uses: actions/checkout@v4              # 코드 저장소
      - uses: actions/checkout@v4              # 비공개 데이터 저장소
        with:
          repository: <owner>/this-week-taste-data
          token: ${{ secrets.DATA_REPO_TOKEN }}
          path: _data
      - run: make setup
      - run: |
          for s in $(sources); do
            python -m pipeline.snapshot --source $s || failed="$failed $s"
            python -m pipeline.diff --source $s || failed="$failed $s"
          done
        env:
          THIS_WEEK_TASTE_DATA_DIR: ${{ github.workspace }}/_data
          GH_TOKEN: ${{ github.token }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          THIS_WEEK_TASTE_UA: "ThisWeekTaste/1.0 (+https://<도메인>/about)"
      - run: |                                  # 데이터 저장소에만 커밋한다
          cd _data
          git config user.name "github-actions[bot]"
          git commit -am "data: $(date +%G-W%V) 스냅샷"
          git push
```

**작성 전에 확인할 것:**
- 각 단계는 이상 상황에서 **비영 종료**한다(2.4). Actions가 실패로 표시하고 Issue가 생긴다 —
  의도된 동작이므로 `continue-on-error`를 붙이지 말 것
- 소스 하나가 실패해도 나머지는 계속 가야 한다(2.3). `&&`로 잇지 말 것
- **사람이 발행하기 전에 데이터 저장소를 `git pull` 해야 한다.** Actions가 거기에 커밋하므로
- GS25를 붙이면 cron 시각이 **KST 13:00~17:45**로 제약된다(robots.txt `Visit-time`)

### 필요한 secret

| 이름 | 무엇 | 누가 만드나 |
|---|---|---|
| `DATA_REPO_TOKEN` | 비공개 데이터 저장소 push 권한. **권한을 그 저장소 하나로 좁힌다** | 사람이 GitHub에서 발급 |
| `GH_TOKEN` | 이상 시 Issue 생성. `${{ github.token }}`으로 대체 가능 | 자동 |
| `THIS_WEEK_TASTE_UA` | 도메인이 확정된 뒤 | 사람 |

`ANTHROPIC_API_KEY`는 **필요 없다.** 발행을 자동화하지 않기 때문이다.

---

## 4. 공개 배포 전에 반드시 고칠 것

| # | 항목 | 이유 |
|---|---|---|
| 1 | ✅ ~~User-Agent의 `example.invalid`~~ | 2026-08-24 해결. `https://this-week-taste.vercel.app/about`을 가리킨다 |
| 2 | ✅ ~~`/about` 페이지가 없다~~ | 2026-08-24 해결. `web/app/about/page.tsx`. 수집 방식과 연락 창구(저장소 이슈)를 담았다 |
| 3 | ⏸ **서비스명 미확정** (배포는 저장소 이름으로 했다) | 표시명 '이번주맛'은 여전히 플레이스홀더다. 지금은 저장소 이름으로 배포하고, 이름이 정해지면 `web/config/site.ts`의 `name`·`url`과 `THIS_WEEK_TASTE_UA`를 함께 고친다 |
| 4 | ⚠️ **이미지 핫링크** | 7장에 따라 원본 CDN을 참조한다. 통째로 깨지는 것을 감지하려고 `make check-images`를 두었다(소스별 10건 표본, 통과율 50% 미만이면 실패로 종료). **배포 전에 돌린다.** |

⚠️ **오리온은 이미지 경로가 robots.txt 금지 구역이다.** `disallow: /upload/`인데
제품 이미지가 `/upload/goods/...`에 있다. 목록 경로(`/goods/list/`)는 허용이라
**수집 자체는 규칙을 지킨다.** `make check-images`도 스스로 요청을 거부한다.
남는 문제는 우리가 발행한 주소를 방문자 브라우저가 불러온다는 것이다 —
robots.txt는 크롤러 지침이지 브라우저 지침이 아니지만, `/about`에
"차단된 곳은 우회하지 않는다"고 적어둔 것과는 결이 어긋난다.

**세 값이 어긋나면 안 된다**: `web/config/site.ts`의 `url` /
`web/app/about/page.tsx`의 존재 / `THIS_WEEK_TASTE_UA`.
UA가 없는 페이지를 가리키면 그건 연락 가능한 식별자가 아니다.
