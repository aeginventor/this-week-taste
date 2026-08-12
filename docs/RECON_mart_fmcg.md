# 정찰 — 마트(6) / 식품 대기업(20)

조사일: 2026-08-11
방법: curl / urllib 직접 요청, 요청 간 1초 이상 간격. 원본 샘플은 `scratch/samples/`.
홈플러스 API 파라미터 1건만 브라우저 Network 탭으로 확인(CLAUDE.md 5장 권장 절차).
**우회 시도 없음.** robots.txt 금지와 WAF 차단은 그대로 기록하고 멈췄다.

---

## 0. 결론 먼저

세 줄 요약:

1. **마트 채널은 v1에서 사실상 붕괴한다.** 이마트(P0)와 롯데마트(P1)의 온라인몰이
   robots.txt로 전면 차단되어 있다. 정상 접근 가능한 대형마트는 **홈플러스 하나뿐**이다.
2. **식품 대기업은 예상대로 보도자료가 옳다.** 다만 이유가 "더 빨라서"가 아니라
   **자사몰 쪽이 막혀 있거나 죽어 있어서**다(남양몰은 운영 종료).
3. **오리온이 이번 정찰의 최대 수확이다.** 유일하게 구조화된 신제품 카탈로그를
   제공한다. FMCG인데 편의점급으로 다루기 쉽다.

---

## 1. 마트 요약표

| 소스 | 등급 | 접근 방법 | robots.txt | 비고 |
|---|---|---|---|---|
| 이마트 | **BLOCKED** | — | ❌ `User-agent: * / Disallow: /` | 뉴스룸으로 우회 |
| 트레이더스 | **BLOCKED** | — | ❌ 이마트와 동일 도메인 | 뉴스룸 기사에 포함됨 |
| 롯데마트 | **BLOCKED** | — | ❌ 롯데온 `Disallow: /` + WAF 403 | 대체 경로 없음 |
| 홈플러스 | **EASY** | XHR(JSON) | ⭕ 관대함 | **유일하게 온전히 열림** |
| 코스트코 | **MEDIUM** | Playwright 필요 | 파일 없음 | 회원제가 문제가 아니었음 |
| 하나로마트 | **N/A** | — | — | targets.yml URL이 틀림 |

---

## 2. 이마트 — BLOCKED (P0인데 막혔다)

### robots.txt가 우리를 명시적으로 배제한다
`https://emart.ssg.com/robots.txt` → 200. 마지막 블록이 결정적이다.

```
User-agent: Googlebot / Yeti / Bingbot / Daum / Baiduspider ...
Allow: /item/itemView.ssg
Allow: /disp/category.ssg
...
User-agent: *
Disallow: /                 ← 우리가 여기 해당한다
```

`https://www.ssg.com/robots.txt`도 **동일하게 `User-agent: * → Disallow: /`**.
지정된 검색엔진 봇에만 상품 경로를 열어두는 구조다.

CLAUDE.md 5장("robots.txt를 확인하고 존중한다. 막힌 경로는 크롤링하지 않는다")에 따라
**SSG 계열 전체를 크롤링 대상에서 제외**한다. UA를 검색엔진으로 위장하는 것은
명시적 배제 의사를 무시하는 것이므로 검토하지 않았다.

### PB 전용 사이트도 없다
| 도메인 | 결과 |
|---|---|
| `news.emart.com` | DNS 미해결 |
| `www.nobrand.co.kr` | DNS 미해결 |
| `www.peacock.co.kr` | DNS 미해결 |
| `www.emart.com` | → `store.emart.com` 리다이렉트 (매장 안내 성격) |

**노브랜드·피코크 신상이 모인 별도 페이지는 존재하지 않는다.**

### 유일한 대체 경로 — 신세계그룹 뉴스룸 (WordPress REST API)

`https://www.shinsegaegroupnewsroom.com/` — robots.txt가 `Allow: /`이고,
**워드프레스 REST API가 인증 없이 완전히 열려 있다.** 마트 채널에서 확보한
유일한 깨끗한 JSON 소스다.

```
GET https://www.shinsegaegroupnewsroom.com/wp-json/wp/v2/posts
    ?family=2&categories=11&after=2026-07-01T00:00:00&per_page=100
    &_fields=id,date,link,title,content
```

- `family` = 브랜드 택소노미 — **이마트=2, 이마트24=3**, 신세계푸드=91, 이마트에브리데이=97
- `categories` = **보도자료=11**, 언론기사=12
- 응답 헤더 `X-WP-Total` / `X-WP-TotalPages`로 전체 건수 확인 가능
- `after=` 파라미터로 **주 단위 증분 수집이 그대로 된다**

부수 효과: `family=3`으로 **이마트24 보도자료**도 같은 API에서 얻는다.
편의점 정찰(`RECON_convenience.md`)에서 이마트24는 행사·PB 목록만 확보했으므로 보완재가 된다.

### ⚠️ 사용자 우려("신상품이지 온라인 할인상품이 아님")가 실측으로 확인됐다

2026-07-01 이후 이마트 보도자료 **21건**을 전수 확인한 결과:

| 성격 | 건수 | 예시 |
|---|---|---|
| 할인/행사 | 18 | "고래잇 페스타 최대 반값", "복날 보양식 최대 반값 할인" |
| **실제 신제품** | **3** | 노브랜드X복순도가 협업 6종, Ditsch 소금버터 프레첼, 이색 디저트 빙수 밀키트 |

**신제품 비율 14%. 주당 약 0.5건.** 마트 보도자료는 대부분 가격 행사 홍보다.
LLM 편집 단계에서 이 둘을 가르는 것이 마트 채널의 핵심 과제가 된다.

### 본문 품질은 좋다
`scratch/samples/shinsegae_emart_post_pretzel.json` (프레첼 출시 기사, 본문 1,288자):
제품명 `디치 소금버터 프레첼 스틱(10입)`, 정상가 `15,980원`, 판매 채널(트레이더스),
용량(84g), 특징까지 모두 본문에 있다. 추출 가능한 수준이다.

단, **가격이 모호하다** — 같은 본문에 정상가 15,980원 / 할인가 13,980원 /
적립 500원이 섞여 있다. 어느 것이 `price`인지 규칙을 먼저 정해야 한다.

---

## 3. 롯데마트 — BLOCKED (대체 경로도 없음)

### targets.yml의 URL이 낡았다
`https://www.lottemart.com` → **`https://lottemartzetta.com`으로 리다이렉트**된다.
온라인몰이 "롯데마트 제타"로 리브랜딩됐다(설명: "온라인 신선 장보기 몰").

### 세 경로 모두 막힌다
| 경로 | 결과 |
|---|---|
| `www.lotteon.com` (롯데온) | robots.txt **`User-agent: * → Disallow: /`** |
| `lottemartzetta.com/products` | robots는 허용하나 **CloudFront WAF가 HTTP 403** ("Request blocked") |
| `www.lotte.co.kr/pr/newsList.do` (롯데지주) | 접근은 되나 **신제품 기사가 없다** |

`lottemartzetta.com/robots.txt`는 `Allow: /`에 `Disallow: /api/`만 두고 있어
**데이터 경로(/api/)는 명시적으로 금지**돼 있고, 그 앞단인 `/products`마저 WAF가 막는다.

롯데지주 뉴스룸 1페이지(9건)를 확인했으나 전부 그룹 경영·인사·ESG 기사였다.
지주사 레벨이라 상품 소식이 올라오지 않는다.

**→ 롯데마트는 v1에서 제외한다.** 우회 없이 접근 가능한 경로가 없다.

---

## 4. 홈플러스 — EASY ⭐ 마트 채널의 유일한 정상 소스

### robots.txt가 오히려 관대하다
`https://front.homeplus.co.kr/robots.txt` → `https://mfront.homeplus.co.kr/robots.txt`로 이동.
```
User-agent: *
Disallow: /favorite
Disallow: /mypage
Content-Signal: ai-train=yes, search=yes, ai-input=yes
Sitemap: https://mfront.homeplus.co.kr/sitemap.xml
```
상품·카테고리 경로는 전부 허용. `Content-Signal`로 AI 이용까지 명시적으로 허용한다.
crawl-delay 없음.

### 엔드포인트
```
GET https://mfront.homeplus.co.kr/category/item.json
    ?categoryDepth=2&categoryId=200002&page=1&perPage=100&sort=RANK
```
응답: **깔끔한 JSON**. 세션·토큰·storeId **모두 불필요**.

> **`sort=RANK`가 필수다.** 이 파라미터가 빠지면 서버가 `returnCode: SUCCESS`에
> `totalCount: 0`을 돌려준다. 에러가 아니라 빈 결과라서 원인을 찾기 어렵다.
> (파라미터 추측으로는 끝내 못 찾았고, 브라우저 Network 탭에서 실제 호출을 보고 확인했다.)

### 카테고리 트리 — 1회 요청으로 전부
```
GET https://mfront.homeplus.co.kr/category/mobile/getMap.json     (163KB)
```
최상위 27개 그룹 → **리프 카테고리 359개**, 그중 **식품 계열 116개**.
`cateDepth`가 `L`/`M`/`S` 문자로 오므로 `categoryDepth` 숫자(1/2/3)로 변환해야 한다.

### 페이지네이션
`perPage`는 **100까지 존중**된다. 200 이상은 HTTP 500.
`pagination.totalCount` / `totalPage`로 사전에 요청 수를 계산할 수 있다.

### 추출 가능 필드 (`data.dataList[]`)
| 필드 | 가능 | 키 |
|---|---|---|
| 제품명 | ⭕ | `itemNm` — **절삭 없음**. "씨제이 비비고 물만두 315G" 형태로 브랜드+용량 포함 |
| 가격 | ⭕ | `salePrice`(정상가), `dcPrice`/`dcRate`(할인) — **분리돼 있어 유리하다** |
| 고유 ID | ⭕ | `itemNo` (예: `070740031`) — 내부 코드. 바코드는 아님 |
| 카테고리 | ⭕ | `lcateNm`/`mcateNm`/`scateNm` 3단계가 응답에 들어있음 |
| 이미지 | ⭕ | `imgChgDt` + 별도 규칙 (`image.homeplus.kr`) |
| 행사 여부 | ⭕ | `eventInfoList`, `stickerEventList` |
| 브랜드 | ❌ | `brandNm`이 **전 항목 빈 문자열**. 사용 불가 |

`salePrice`와 `dcPrice`가 나뉘어 있는 점이 중요하다 — 사용자가 우려한
"할인상품과 신상품 혼동"을 **데이터 레벨에서 구분할 수 있다.**

### ⚠️ 온라인 카탈로그 ≠ 오프라인 매장 (우려가 실측으로 확인됨)

카테고리별 실측 건수:

| 카테고리 | 건수 | 카테고리 | 건수 |
|---|---|---|---|
| 과일 / 사과·배 | **0** | 우유/유제품 / 치즈·버터 | 167 |
| 과일 / 딸기·체리 | **0** | 우유/유제품 / 요거트 | 152 |
| 과일 / 수박·메론 | 3 | 냉장냉동 / 떡볶이·면류 | 118 |
| 커피/차 / 커피믹스 | **0** | 냉장냉동 / 피자·핫도그 | 81 |

**신선식품은 사실상 비어 있고 가공식품만 채워져 있다.** 온라인 배송 가능 품목만
노출되는 구조로 보인다. 우리 서비스는 가공 식음료 신상이 대상이므로
**실질적 손해는 크지 않지만, "홈플러스 전체 카탈로그"라고 부르면 안 된다.**

### PB — 별도 페이지는 없다
- 카테고리 응답에 **`홈플러스시그니처` 접두사가 붙은 상품이 그대로 섞여 있다.**
  실측 예: `홈플러스시그니처 100% 한우곰탕 1KG` (5,490원),
  `홈플러스시그니처 멸치아몬드볶음 80G` (3,990원) 등.
- `brandNm`이 비어 있으므로 **`itemNm` 접두사 매칭으로 PB를 식별**해야 한다.
- `심플러스`는 **기획전(EXH)으로 존재**한다:
  `category/mobile/dspCateTheme.json` → 배너 `심플러스`, `linkType: EXH`,
  `linkInfo: 18930`, `exhStoreType: HYPER`.
  기획전 상품 목록 엔드포인트는 **파라미터를 확정하지 못했다**(`exhibition.json`에
  여러 이름을 시도했으나 전부 HTTP 500). 필요해지면 브라우저로 1회 관측하면 된다.

### 요청 수 추정
식품 리프 116개, 대부분 100건 이하 → **약 150~200 요청**.
카테고리 트리 1회 + 1초 간격 → **3~4분**.

---

## 5. 코스트코 — MEDIUM (회원제는 문제가 아니었다)

사용자 질문에 대한 답: **회원제 때문에 막힌 것이 아니다.**

| 확인 항목 | 결과 |
|---|---|
| robots.txt | **존재하지 않음** — 어떤 경로를 요청해도 SPA 셸(HTML)을 반환 |
| 상품 상세(PDP) | **로그인 없이 완전 공개.** `<title>노비타 BD-H721H0 비데`, `"price":"286900.0"` |
| 홈페이지 | **프리렌더링됨.** 상품 90개·가격 119개가 HTML에 이미 들어있음 |
| 카테고리 목록 | **비어 있음.** `/Foods/c/cos_10` 700KB를 받아도 상품 링크 0개 |
| 사이트맵 | 없음 (`/sitemap.xml` 등 전부 SPA 셸) |
| OCC API | `/occ/v2/...` 전부 SPA 셸. `occBaseUrl`이 지연 로딩 청크에 있어 정적 분석으로 미확보 |

플랫폼은 **SAP Spartacus(Angular)**다. 즉 상품 데이터는 공개돼 있는데
**목록을 열거할 방법이 없다.** 전체 카테고리 트리는 홈 HTML에 들어 있어
(`/Foods/c/cos_10` 등 식품 카테고리 경로 확보 완료) 진입점은 있다.

**판정: MEDIUM.** 회원 가입이 아니라 **Playwright가 필요**하다.
CLAUDE.md 5장이 Playwright를 최후의 수단으로 두므로 **P2 유지**를 권한다.

---

## 6. 하나로마트 — targets.yml이 틀렸다

- `www.nhhanaromart.co.kr` → **DNS SERVFAIL** (도메인 자체가 없음)
- `www.hanaromart.co.kr` → 접속은 되나 `<title>CNKiSoft Homepage</title>` — **무관한 회사 사이트**
- 실제 농협 온라인몰은 **`https://www.nonghyupmall.com`** (농협몰 / e-하나로마트). robots.txt 없음(404)

다만 농협몰은 **산지직송 농축산물 중심**이라 우리가 찾는 가공 식음료 신상과
성격이 다르다. **P2 유지하되 우선순위를 더 낮추는 쪽**을 권한다.

---

## 7. 식품 대기업(FMCG) — 뉴스룸 vs 자사몰

### 결론: 뉴스룸이 맞다. 단 이유가 예상과 다르다

사용자 가설은 "자사몰보다 뉴스룸이 더 빠르고 정확할 것"이었다. 실측 결과 **맞다.**
그런데 근거는 속도가 아니라 **자사몰 쪽이 아예 선택지가 아니기 때문**이다.

- **남양유업 자사몰은 운영을 종료했다** (`shopping.namyangi.com` → "남양몰 운영 종료 안내")
- 대형 자사몰(CJ더마켓 등)은 이마트·롯데와 같은 커머스 플랫폼 계열이라 차단 위험이 동일
- 반면 **보도자료 제목에 "출시"가 그대로 박혀 있어** 신제품 판별이 자명하다
  (예: `샘표, '저당 장아찌 간장' 출시`)

추가로, **자사 제품 카탈로그(자사몰이 아닌 기업 사이트의 제품 소개 페이지)**라는
제3의 경로가 있고, 이쪽이 diff와 가장 잘 맞는다.

### 등급표 (20개사)

| 소스 | 등급 | 경로 | 최신 갱신 | 비고 |
|---|---|---|---|---|
| **오리온** | **EASY ⭐** | `/goods/list/25?badge=new` | 활성 | **구조화된 신제품 카탈로그** |
| 롯데웰푸드 | EASY | `/prcenter/news` | 2026-07-27 | 서버 렌더링, 출시 기사 다수 |
| 샘표 | EASY | `/news/press-release` | 2026-07-31 | **신제품 밀도 최고**(25건 중 5건) |
| 오비맥주 | EASY | `/newsroom/list.php` | 2026-08-10 | 활발 |
| CJ제일제당 | EASY | `/kr/newsroom/pressreleases` | 2026-08-10 | 서버 렌더링 |
| 하이트진로 | EASY | `/socialmedia/press_list.asp` | (본문 확인) | 출시 기사 확인 |
| 동원F&B | EASY | `/services/Customer/News/News_List` | 2026-08-11 | 오늘자 기사 존재 |
| 크라운 | EASY | `/sns/news` | 2026-07-31 | 제품 카탈로그(`/product/index`)도 서버 렌더링 |
| 빙그레 | EASY | `/news/news_announced` | 2026-08-11 | `/news/news_new`(신제품)는 2026-06-02로 갱신 느림 |
| 오뚜기 | MEDIUM | `otoki.com/pr/news` | JS 렌더링 | **도메인 변경**: ottogi.co.kr → **otoki.com** |
| 대상 | MEDIUM | `/kr/pr/news.jsp` | JS 렌더링 | 목록이 HTML에 없음 |
| 농심 | MEDIUM | `/promotion/news_list` | JS 렌더링 | ⚠️ **TLS 이슈** 아래 참조 |
| 서울우유 | 저가치 | `/enterprise/company/jnews_list.sm` | **2026-04-02** | 4개월째 정지 |
| 해태제과 | 저가치 | `/sweet/news` | **2024-04-21** | 2년 이상 정지 |
| 남양유업 | HARD | — | — | **자사몰 운영 종료** |
| 삼양식품 | 미확인 | — | — | 홈이 게이트 페이지, 경로 미발견 |
| 풀무원 | 미확인 | — | — | HTTP 417 (Expectation Failed) |
| 매일유업 | 미확인 | `/news/press.jsp` | 판별 불가 | 응답은 오나 목록 구조 미확인 |
| 롯데칠성 | 미확인 | — | — | `company.lottechilsung.co.kr`, 뉴스 링크 미발견 |
| 동아오츠카 | 미확인 | `/sub4/sub1.asp?t_name=BOARD11` | 판별 불가 | 게시판 구조 |

> ⚠️ **농심 TLS**: 기본 설정으로는 `SSLV3_ALERT_HANDSHAKE_FAILURE`가 난다.
> `DEFAULT@SECLEVEL=1`로 낮춰야 접속된다. 서버가 낡은 암호 스위트만 지원한다는 뜻이므로
> 스크래퍼에 소스별 TLS 예외가 필요하다. (봇 차단이 아니라 서버 노후 문제)

### ⭐ 오리온 — 이번 정찰의 최대 수확

```
GET https://www.orionworld.com/goods/list/25?badge=new     ← 신제품 목록
GET https://www.orionworld.com/goods/list/26?category=0101 ← 카테고리별 전체
```
**서버 렌더링 HTML.** 실측 결과 8건이 깔끔하게 나온다:

```
goodsno=178  오!그래놀라 저당 카카오
goodsno=176  미쯔 황치즈
goodsno=175  오뜨 애플파이
goodsno=174  초코송이 말차
goodsno=173  스윙칩 까르보나라불닭맛
goodsno=172  지지미
goodsno=171  비쵸비 딸기
goodsno=170  오!그래놀라 오리지널
```

- **제품명 절삭·POS 접두사 없음** (편의점 4사의 고질적 문제가 여기엔 없다)
- **`goodsno`라는 안정적 정수 ID**
- `?category=0101` 형태로 **전체 카탈로그 스냅샷도 가능** → CLAUDE.md 2.1 차집합이 그대로 통한다

`?badge=new`는 소스의 신상 라벨이므로 CLAUDE.md 2.1에 따라 **판별에는 쓰지 않고**,
전체 카탈로그 diff를 정본으로 하되 `badge=new`는 **검증용 대조군**으로 쓰는 것을 권한다.

---

## 8. diff 방식과의 궁합

**보도자료 소스는 diff가 필요 없다.** 이 점이 편의점 정찰과 결정적으로 다르다.

| 소스 유형 | 해당 소스 | 신상 판별 방식 |
|---|---|---|
| **전체 카탈로그** | 홈플러스, 오리온, 크라운 | 차집합 (CLAUDE.md 2.1 그대로) |
| **추가 전용 피드** | 이마트 뉴스룸, FMCG 보도자료 8곳 | **post id / date 기준 증분** — 지난주 이후 새 글만 |
| **불가** | 이마트몰, 롯데마트, 남양 | — |

보도자료는 게시물이 사라지지 않으므로 "지난주에만 있는 항목 = 단종 후보"라는
개념이 성립하지 않는다. `after=<지난주 발행 시각>`으로 새 글만 가져오면 되고,
이쪽이 오히려 더 안정적이다.

**대신 어려움이 diff에서 추출로 이동한다.** 보도자료는 구조화 데이터가 아니라
산문이므로, 기사 1건에서 제품 N개를 뽑아내는 작업이 필요하다.

> 📌 **CLAUDE.md 6장과 충돌한다.** 현재 LLM의 역할은 "판단이지 창작이 아니다"로
> 4가지(신제품 판별/중복 병합/분류/한 줄 설명)만 규정돼 있다. 보도자료 소스는
> **5번째 역할 "본문에서 제품 레코드 추출"**을 요구한다.
> 코드를 짜기 전에 CLAUDE.md 6장을 먼저 고쳐야 한다.

---

## 9. 제품 고유 ID

| 구분 | 소스 |
|---|---|
| 안정적 내부 ID | 홈플러스(`itemNo`), 오리온(`goodsno`), 신세계 뉴스룸(WP `id`) |
| 바코드 | **없음** — 마트·FMCG 채널에서 바코드를 주는 소스는 하나도 없다 |
| 이름 해시 필요 | 보도자료에서 추출한 모든 제품 |

편의점 채널은 바코드가 나왔지만(CU·GS25·이마트24) **마트/FMCG는 전무하다.**
따라서 **채널 간 동일 제품 대조는 불가능**하다고 보는 편이 안전하다.
예를 들어 "오리온 스윙칩 까르보나라불닭맛"이 CU에도 들어와도 두 레코드를 이을 수 없다.
LLM 중복 병합 단계가 이름 기반으로 이 부담을 떠안게 된다.

---

## 10. 현 시점 리스크 3가지

1. **P0 소스 이마트가 robots.txt로 차단됐다.**
   마트 채널에서 정상 접근 가능한 곳은 홈플러스 하나뿐이다.
   targets.yml의 "P0 = 24개" 전제가 깨졌다. 이마트를 뉴스룸 기반으로 재정의하거나,
   마트 채널 자체를 v1 범위에서 내리는 판단이 필요하다.

2. **보도자료 기반 소스는 파이프라인 모양이 다르다.**
   스냅샷→차집합이 아니라 증분 피드→본문 추출이다. `pipeline/diff.py`가
   이 소스들에는 적용되지 않는다. 소스 유형이 두 종류로 갈리는 것을
   설계에 반영하지 않으면 나중에 크게 꼬인다.

3. **마트 보도자료의 신호 대 잡음비가 낮다.**
   이마트 실측 기준 21건 중 신제품 3건(14%). 나머지는 할인 행사다.
   LLM이 이를 못 가르면 "이번주 신상"에 반값 수박이 올라온다.
   반대로 FMCG 보도자료는 밀도가 훨씬 높다(샘표 25건 중 5건).

---

## 11. 다음 단계 권고

CLAUDE.md 8장의 순서(CU 수직 관통 → 2주 검증 → 확장)는 그대로 유지한다.
이 정찰 결과는 **4단계(확장)에서 쓸 재료**이며, 확장 시 우선순위는:

1. **오리온** — 편의점급으로 쉽고 ID·이름 품질이 가장 좋다. 카탈로그 diff 그대로 적용
2. **홈플러스** — 마트 채널 유일 생존자. 요청 수도 감당 가능
3. **신세계그룹 뉴스룸** — 이마트+이마트24를 한 API로. 단 추출 파이프라인 신설 필요
4. FMCG 보도자료 EASY 7곳 — 3번과 같은 추출 파이프라인을 재사용

**롯데마트·남양유업은 v1에서 제외**를 권한다.

---

## 12. 저장된 샘플

```
scratch/samples/
├─ 마트
│   ├─ emart_robots.txt                     ★ User-agent:* Disallow:/ 근거
│   ├─ ssg_robots.txt                       ★ 동일 (www.ssg.com)
│   ├─ lotteon_robots.txt                   ★ 롯데온 Disallow:/
│   ├─ lottemartzetta_robots.txt            Allow:/ 이나 /api/ 금지
│   ├─ lottemartzetta_home.html             리브랜딩 확인
│   ├─ lottemartzetta_products.html         ★ CloudFront 403 본문
│   ├─ lottemart_company_home.html          기업사이트(보도자료 없음)
│   ├─ lotte_pr_newsList.html               ★ 롯데지주 뉴스 9건(제품 기사 없음)
│   ├─ lotte_pr_newsList_post.html          POST 시도 결과
│   ├─ homeplus_robots.txt                  ★ 관대함 + Content-Signal
│   ├─ homeplus_sitemap.xml                 mart/ssm 분리 구조
│   ├─ homeplus_categories_mart.xml         카테고리 URL 1,355개
│   ├─ homeplus_themes_mart.xml             기획전 3건
│   ├─ homeplus_category_map.json           ★ 전체 카테고리 트리(리프 359)
│   ├─ homeplus_category_item.json          ★ 상품 API 응답(필드 근거)
│   ├─ homeplus_list_200009.html            CSR 확인용(상품 없음)
│   ├─ homeplus_home.html
│   └─ nonghyupmall_robots.txt              404 응답
├─ 신세계 뉴스룸
│   ├─ shinsegae_newsroom_robots.txt        ★ Allow:/
│   ├─ shinsegae_newsroom_home.html         /family/emart 구조
│   ├─ shinsegae_wp_posts.json              ★ WP REST 기본 응답
│   ├─ shinsegae_emart_press_july.json      ★ 이마트 보도자료 21건(신제품 비율 근거)
│   └─ shinsegae_emart_post_pretzel.json    ★ 본문 품질 근거
├─ 코스트코
│   ├─ costco_robots.txt                    robots 없음(SPA 셸 반환) 증거
│   ├─ costco_home.html                     ★ 프리렌더링 + 전체 카테고리 트리
│   ├─ costco_foods_c10.html                ★ 카테고리 CSR(상품 0개) 증거
│   ├─ costco_product_detail.html           ★ 비로그인 가격 노출 증거
│   └─ costco_main.js                       Spartacus 확인
└─ FMCG (fmcg_*.html)
    ├─ fmcg_orion_new.html                  ★ badge=new 신제품 8건
    ├─ fmcg_orion_cat.html                  카테고리 카탈로그
    ├─ fmcg_sempio_press.html               ★ 신제품 밀도 최고
    ├─ fmcg_lottewell_news.html             ★ 출시 기사
    ├─ fmcg_ob_press.html                   ★ 2026-08-10
    ├─ fmcg_cj_press.html                   ★ 2026-08-10
    ├─ fmcg_dongwon_press.html              2026-08-11
    ├─ fmcg_hitejinro_press.html            출시 기사
    ├─ fmcg_binggrae_press.html / _newproduct.html
    ├─ fmcg_crown_products.html             제품 카탈로그 서버 렌더링
    ├─ fmcg_seoulmilk_press.html            2026-04 정지 증거
    ├─ fmcg_haitai_press.html               2024-04 정지 증거
    ├─ fmcg_ottogi_news.html / fmcg_daesang_news.html   CSR 증거
    └─ fmcg_*_home.html                     각 사 홈(경로 탐색 근거)
```
