# 배포 / 확인 방법

`web/`은 순수 정적 사이트다(`output: "export"`). 서버 런타임이 없어서 아무 정적 호스팅에나
올라가고, 빌드 산출물은 `web/out/` 1.1MB다.

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

### 데이터가 저장소 안에 있다는 점이 핵심

CLAUDE.md 2.2에 따라 `data/`의 JSON이 곧 데이터베이스이고 git에 커밋된다.
따라서 **DB도, 백엔드도, 빌드 시 외부 호출도 없다.** `git push` → 호스트가 다시 빌드 →
끝이다. 사이트가 읽는 파일은 `data/weeks/<week>.json` 하나뿐이다.

### 호스팅 설정 (Cloudflare Pages / Vercel / Netlify 공통)

| 항목 | 값 |
|---|---|
| Root directory | `web` |
| Build command | `npm ci && npm run build` |
| Output directory | `out` |
| Node version | 20 이상 |

> ⚠️ **저장소 전체가 체크아웃돼야 한다.** `web/lib/weeks.ts`가 `../data/weeks`를 읽으므로
> `web/`만 잘라서 배포하면 빈 사이트가 나온다. 대부분의 호스트는 저장소 전체를 받고
> Root directory에서 빌드만 실행하므로 기본 동작으로 충분하다.

GitHub Pages를 쓴다면 Actions에서 `web/out`을 아티팩트로 올리면 된다. 다만 사용자 페이지가
아닌 프로젝트 페이지(`/<repo>/` 하위 경로)에 올릴 경우 `basePath` 설정이 추가로 필요하다.

### 발행된 주차가 없을 때

홈이 "아직 발행된 주차가 없습니다"를 명시적으로 보여준다(CLAUDE.md 2.4 — 조용한 빈 페이지
금지). 배포는 성공하는데 화면이 비어 있다면 `data/weeks/`에 파일이 없는 것이다.

---

## 3. 주간 자동화 (8장 5단계 — **아직 만들지 않았다**)

사람 손을 매주 타지 않으려면 이게 필요하다. 형태는 이렇게 된다:

```yaml
# .github/workflows/weekly.yml (미작성)
on:
  schedule:
    - cron: "0 1 * * 1"     # 매주 월요일 KST 10:00
  workflow_dispatch:
jobs:
  collect:
    steps:
      - uses: actions/checkout@v4
      - run: make setup && make week
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GH_TOKEN: ${{ github.token }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          THIS_WEEK_TASTE_UA: "ThisWeekTaste/1.0 (+https://<도메인>/about)"
      - run: |                        # 9장: 데이터 커밋과 코드 커밋을 섞지 않는다
          git config user.name "github-actions[bot]"
          git commit -am "data: $(date +%G-W%V) snapshot (cu)"
          git push
```

데이터가 커밋되면 호스트가 알아서 다시 빌드한다. 별도 배포 단계가 필요 없다.

**작성 전에 확인할 것:**
- `make week`는 이상 상황에서 **비영 종료**한다(2.4). Actions가 실패로 표시하고 Issue가 생긴다 —
  의도된 동작이므로 `continue-on-error`를 붙이지 말 것
- GS25를 붙이면 cron 시각이 **KST 13:00~17:45**로 제약된다(robots.txt `Visit-time`). CU만이면 무관
- 소스가 늘면 소스별로 job을 나눠야 한다(2.3 격리). 한 소스 실패가 나머지를 막으면 안 된다

---

## 4. 공개 배포 전에 반드시 고칠 것

| # | 항목 | 이유 |
|---|---|---|
| 1 | **User-Agent의 `example.invalid`** | 5장은 *연락 가능한* 식별자를 요구한다. 지금 값으로 공개 크롤링하면 규칙 위반이다. `THIS_WEEK_TASTE_UA`로 덮어쓸 것 |
| 2 | **`/about` 페이지가 없다** | UA가 `+https://<도메인>/about`을 가리키는데 그 페이지가 존재하지 않는다. 사이트 소개 + 수집 방식 + 연락처를 담은 페이지를 만들어야 UA의 약속이 지켜진다 |
| 3 | **서비스명 미확정** | 도메인이 이름에 묶인다. `web/config/site.ts` 한 곳만 고치면 되도록 해뒀다 |
| 4 | **이미지 핫링크** | CU CDN을 직접 참조한다(7장에 따라 의도된 것). 공개 시 그쪽에 트래픽이 붙고, 차단되면 이미지가 조용히 깨진다. CDN 호스트명이 난수 문자열이라 언제든 바뀔 수 있고 깨진 이미지를 감지할 장치가 아직 없다 |

1·2번은 크롤링 예절 문제라 **공개 여부와 무관하게 지금 값이 잘못돼 있다.**
자동화를 붙이기 전에 먼저 고치는 편이 낫다.
