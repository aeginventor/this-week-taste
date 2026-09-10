# 배포 / 확인 방법

Git 자동 배포는 `main`에만 허용한다. 나머지 브랜치는 이름과 무관하게 차단한다.
`vercel.json`은 `**: false`, `main: true`를 사용한다. [Vercel 공식 규칙](https://vercel.com/docs/project-configuration/git-configuration)에 따라 여러 패턴 중 true가 우선한다(2026-09-10 확인).
`main` push는 배포를 일으킬 수 있으므로 정리 결과 확인 전에는 하지 않는다.

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

## 2026-09-09 발행 계약 변경

2026-09-10 제품 방향 변경: [ADR-0020](adr/0020-new-products-and-upcoming.md)에 따라 화면은 신상·출시 예정 소개를 유지한다.
아래의 발견/출시 미확인 화면 설명은 이전 설계 기록이며 현재 UI에 적용하지 않는다. 발행 입력 검증과 과거 공개 파일 보존은 유지한다.

새 발견과 출시 확인을 구분한다. 현재 구현은 출시 미확인 상태와 관측 근거를 표시한다.
공식 출시 근거 수집은 후속 검증 단계이며 이번 변경은 아직 배포하지 않았다.

- 새 diff는 관측·원본·코드의 지문을 기록한다. 옛 diff는 스냅샷을 보존한 채 `make diff SOURCE=... WEEK=...`로 재생한다.
- 보강은 그 diff와 연결한다. 옛 보강 파일은 자동 신뢰하지 않으므로 `make enrich`로 재생하거나 검증된 원본 재처리 절차가 필요하다. 연결이 없으면 경고 후 보강 없이 발행한다.
- `make publish`는 같은 주차의 부분 산출물을 만든다. 이전 공개 ID를 보존한다.
- `make week-all`은 실패한 소스를 병합에 전달한다. 근거가 그대로인 이전 성공본만 유지하고 수집 시점을 표시한다.
- `make merge`는 모든 부분 파일의 입력·형식·내용을 검사한다. 옛 부분 파일과 변경된 입력의 파일은 삭제하지 않고 제외한다. 유효한 부분이 하나도 없으면 실패하며 기존 주간 파일은 보존한다.
- 코드 변경도 이전 증명을 무효로 만들 수 있다. 코드의 일부 주석 수정에도 재생이 필요할 수 있는 보수적인 계약이다. 운영 부담을 측정해 더 좁힐지 결정한다.
- 원본 refresh는 이번 이행에 필요하지 않다. 동시에 여러 프로세스로 같은 주차를 수정하지 않는다.
- 주간 JSON과 리포트의 generation_id가 다르면 병합을 재실행한다. 웹은 주간 JSON을 읽으며 과거 형식도 계속 읽는다.

검증만 할 때는 운영 `data/weeks`·`data/published`에 쓰지 않는다. 테스트는 임시 디렉터리를
사용한다. 실제 자료의 읽기 전용 판별 비교는 `python -m scripts.audit_discovery`로 한다.
전체 발행 재생의 조건과 격리 경로는 [작업 기록](../learning/sessions/2026-09-09-발견과-출시를-분리한-설계-검토.md)을 따른다.
배포 전에는 기존 `make test`, `make site`, `make check-images` 확인을 유지한다.

현재 발행 CLI의 실제 실행 파일은 `claude -p`다. 2026-09-07에는 GitHub schedule이
발화했으며 일부 소스 실패로 전체 run이 실패했다. 아래의 이전 cron 미발화 설명은
당시 기록이고 현재 운영 상태는 위 작업 기록의 실행 링크에서 확인한다.

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

2026-09-10 확인한 현재 경계다. 작업 브랜치의 예약 수정은 **main 반영 전에는 실행되지 않는다**.

| 단계 | 자동 실행 범위 | 필요한 사람의 작업 |
|---|---|---|
| Actions 수집 | 등록된 18개 카탈로그 중 러너에서 가능한 15개, snapshot → diff → 비공개 데이터 main push | 실패·이월 원인 판단, 필요 시 재시도 |
| 로컬 수집 | 정기 실행 장치 없음 | 컴포즈·맘스터치·파리바게뜨 3개를 로컬에서 실행 |
| 보강·LLM 편집 | Actions에서 실행하지 않음 | 인증된 로컬 CLI 또는 별도 API 환경에서 실행 |
| 콘텐츠 후보 | 정기 수집기 없음 | 상품 사실·출처·날짜·과거 관측 대조 후 비공개 후보 파일 작성 |
| 병합·발행 | 검토 후보와 유효한 부분 산출물을 로컬 명령으로 병합 | 결과·이미지·웹 빌드 확인, 공개 발행 파일 커밋 |
| 사이트 배포 | 코드 main push에 연결 | 이번 변경은 미리보기 확인 후 main 반영 승인 |

작업 브랜치의 `.github/workflows/weekly.yml`은 월요일 KST 10:13·12:13 두 번 수집한다.
이미 성공한 같은 주차는 재사용하고, 소스별 실제 관측 주차·이월·누락·형식을 실행 요약에 남긴다.
파일이 있다는 것만으로 성공으로 세지 않는다. 상태 검사는 실패해도 실행하고, 성공한 소스의 데이터 커밋은 유지한다.

```bash
THIS_WEEK_TASTE_DATA_DIR=/path/to/private-data .venv/bin/python -m scripts.collection_status --week 2026-W37
```

이 명령은 읽기 전용이며 하나라도 미수집·이월·잘못된 관측이면 비영 종료한다.
반면 **Actions 자체가 시작되지 않은 경우는 이 workflow 내부에서 발견할 수 없다**.
별도 후속 확인에서 실제 run·소스별 결과·원격 산출물 주차를 대조한다. cron 존재를 실행 성공으로 보고하지 않는다.

발행 전에는 비공개 데이터 원격을 확인하고 새 성공본을 가져온다. 성공 스냅샷을 이유 없이 refresh하지 않는다.
홈플러스처럼 이월된 관측은 성공한 이번 주 수집과 구분한다. GS25는 서비스 대상이며 현재 이 카탈로그 묶음에만 없다.
새 GS25 콘텐츠 정기 수집을 과거 카탈로그 승인으로 대신하지 않는다.

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

## 검토한 콘텐츠 후보를 발행에 연결하기 (ADR-0020)

비공개 데이터 디렉터리의 `candidates/<week>.json`을 사용한다. `version: 1`, `week`, 시간대가 있는
`reviewed_at`, `entries` 목록을 둔다. 각 후보는 고유 `id`, `review`의 include/hold·이유,
포함 후보의 과거 관측 대조·검토 주체, `evidence`의 URL·읽은 범위·원자료 묶음·확인 사실,
`product`의 상품 필드를 기록한다. `tests/test_content_candidates.py`가 최소 입력과 거부 반례를 보여준다.

기존 `make merge WEEK=...`가 포함 후보를 함께 읽는다. 콘텐츠만으로도 발행할 수 있으며 카탈로그
snapshot·diff를 가짜로 만들지 않는다. 명시적인 `catalog_id` 연결만 기존 항목을 보강한다.
출시 예정은 `release_status: upcoming`, 확인 가능한 날짜만 `release_date`에 넣는다.
검토 이유·본문·증거 목록은 공개 상품에 복사하지 않는다. 이 파일을 만드는 정기 수집기는 아직 없다.
