# 정찰 — 편의점 4사 (CU / GS25 / 세븐일레븐 / 이마트24)

조사일: 2026-08-11
방법: curl / urllib 직접 요청, 요청 간 1초 이상 간격. 원본 샘플은 `scratch/samples/`.
**우회 시도 없음.** 차단이 걸린 지점은 그대로 기록했다.

---

## 요약표

| 소스 | 등급 | 렌더링 | 방식 | 전체 카탈로그 노출 | 요청 수 | 항목 수 | robots.txt |
|---|---|---|---|---|---|---|---|
| CU | **EASY** | XHR(HTML 조각) | POST form | ⭕ 전 카테고리 | ~131 | ~5,100 | 파일 없음(404) |
| GS25 | **EASY** | XHR(JSON) | POST + CSRF | ❌ PB·행사만 | ~6 | ~2,510 | 허용, 단 제약 있음 |
| 세븐일레븐 | **MEDIUM** | XHR(HTML 조각) | POST form | ❌ 행사·PB만 | ~35 | ~2,600 | 허용 |
| 이마트24 | **EASY** | 서버 렌더링 | GET 쿼리 | ❌ 행사·PB만 | ~155 | ~3,080 | 허용 |

합계 약 **327 요청 / 13,300 항목**. 1초 간격이면 약 6분(GS25 crawl-delay 반영 시 +1분).

---

## 1. CU — EASY ⭐ 수직 관통 후보로 최적

### robots.txt
`https://cu.bgfretail.com/robots.txt` → **HTTP 404** (파일 자체가 없음).
명시적 금지 규칙이 없으므로 크롤링 허용으로 간주. 크롤 딜레이 지정도 없음.

### 엔드포인트
```
POST https://cu.bgfretail.com/product/productAjax.do
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Referer: https://cu.bgfretail.com/product/product.do?category=product&depth2=4

pageIndex=1&searchMainCategory=10&searchSubCategory=&listType=0
&searchCondition=&searchUseYn=&gdIdx=0&codeParent=10
```
응답: **HTML 조각** (JSON 아님). `<li class="prod_list">` 단위로 파싱.
세션 쿠키·토큰 **불필요**. 헤더 조작 없이 그대로 200.

### 카테고리 코드 (`searchMainCategory` = `codeParent`)
| 코드 | 이름 | 페이지 | 항목 수 |
|---|---|---|---|
| 10 | 간편식사 | 6 | 208 |
| 20 | 즉석조리 | 3 | 101 |
| 30 | 과자류 | 29 | 1,154 |
| 40 | 아이스크림 | 6 | 225 |
| 50 | 식품 | 43 | 1,686 |
| 60 | 음료 | 23 | 888 |
| 70 | 생활용품 | 21 | 838 |
| | **합계** | **131** | **~5,100** |

> ⚠️ **이 표는 소스가 가진 전부이지 우리가 긁는 것이 아니다.**
> `70 생활용품`은 범위 밖이라 `scrapers/cu.py`에 넣지 않았다 —
> 실제 수집은 **6개 카테고리 / 110요청**이다([ADR-0012](adr/0012-collection-scope.md)).
> 2026-08-24에 이 표를 그대로 옮겼다가 티슈·바디로션·가그린이 사이트에 실렸다.
> **정찰 표를 스크래퍼로 복사하기 전에 범위를 먼저 자를 것.**

### 페이지네이션
`pageIndex` 1부터 증가, 페이지당 **40개 고정**(변경 불가).
마지막 페이지 판별: 응답에 `prodListBtn-w`(더보기 버튼)가 없거나 항목이 40개 미만.

### 추출 가능 필드
| 필드 | 가능 | 출처 |
|---|---|---|
| 제품명 | ⭕ | `<div class="name"><p>` |
| 가격 | ⭕ | `<div class="price"><strong>` |
| 이미지 | ⭕ | `<img class="prod_img" src>` (프로토콜 상대 URL `//tqklhszfkvzk...edge.naverncp.com/product/<바코드>.jpg`) |
| 고유 ID | ⭕⭕ | **두 개**. 이미지 파일명 = **바코드**(8809148599009), `view(17620)` = 내부 gdIdx |
| 카테고리 | ⭕ | 요청한 `searchMainCategory` 값으로 역산 |
| 신상 라벨 | ⭕ | `.tag > span.new` — **CLAUDE.md 2.1에 따라 사용하지 않음** |

### 주의사항
- **제품명이 소스 단계에서 잘려 있다.** `샐)오리지널닭가슴살샐러` (샐러드→샐러).
  상세 페이지(`/product/view.do?category=product&gdIdx=17620`)에서도 동일하게 잘려 있으므로
  **우리 파싱 문제가 아니라 CU의 POS 명칭 그대로**다. 12자 내외 상한으로 보인다.
  → LLM 편집 단계에서 이름을 "복원"하게 하면 안 된다(CLAUDE.md 6장: 없는 정보 생성 금지).
- 상세 페이지에는 **상품 설명과 태그**가 있다. 다만 상품당 1요청이므로 v1에서는 쓰지 않는 쪽을 권장.
- 이미지 CDN 호스트명이 난수 문자열이라 교체될 수 있다. 원본 URL 그대로 저장할 것.

---

## 2. GS25 — EASY (단, 전체 카탈로그 아님)

### robots.txt
`http://gs25.gsretail.com/robots.txt` → 200. 상품 경로는 **허용**.
```
Disallow: /gscvs/ko/cart, /checkout, /my-account   ← 상품과 무관
Crawl-delay: 10                                    ← 요청 간 10초
Request-rate: 1/10
Visit-time: 0400-0845                              ← UTC. KST 13:00~17:45
```
⚠️ **`Crawl-delay: 10`과 `Visit-time`을 지켜야 한다.** 총 6요청이므로 60초면 끝나지만,
GitHub Actions cron 시간을 **KST 13:00~17:45 사이**로 잡아야 `Visit-time`을 존중하게 된다.
(`Visit-time`은 비표준 확장이지만 사이트가 명시한 의사이므로 따르는 쪽으로 기록해 둔다.)

### 엔드포인트 — 세션 + CSRF 토큰 필요
첫 요청은 **HTTP 403**이었다. 봇 차단이 아니라 **CSRF 보호**였고,
페이지가 자기 토큰을 HTML에 실어 보내는 정상 흐름을 그대로 따르면 200이 된다.

```
1) GET  http://gs25.gsretail.com/gscvs/ko/products/youus-freshfood
        → JSESSIONID 쿠키 + <input name="CSRFToken" value="..."> 획득
2) POST http://gs25.gsretail.com/gscvs/ko/products/youus-freshfoodDetail-search?CSRFToken=<토큰>
        (같은 쿠키 유지)
        pageNum=1&pageSize=500&searchWord=&searchHPrice=&searchTPrice=
        &searchSrvFoodCK=FreshFoodKey&searchSort=searchALLSort&searchProduct=productALL
```
응답: **JSON** — 단 `json.loads()`를 **두 번** 해야 한다(JSON 문자열 안에 JSON).

| 목록 | 파라미터 | 항목 수 | 요청 수(pageSize=500) |
|---|---|---|---|
| Fresh Food (PB) | `searchSrvFoodCK=FreshFoodKey` | 203 | 1 |
| 차별화 상품 | `searchSrvFoodCK=DifferentServiceKey` | 584 | 2 |
| 행사상품 전체 | 별도 엔드포인트 ↓ | 1,723 | 4 |

행사상품은 엔드포인트가 다르다:
```
POST /gscvs/ko/products/event-goods-search?CSRFToken=<토큰>
     pageNum=1&pageSize=500&searchType=&searchWord=&parameterList=TOTAL
```
`parameterList`: `ONE_TO_ONE`(831) / `TWO_TO_ONE`(881) / `GIFT`(11) / `TOTAL`(1,723)

### 페이지네이션
`pageSize`가 **서버에서 그대로 존중된다**(500까지 확인). `SubPageListPagination.totalNumberOfResults`로
전체 수를 먼저 읽고 한두 번에 끝낼 수 있다. 4사 중 가장 효율적.

### 추출 가능 필드 (`SubPageListData[]`)
| 필드 | 가능 | 키 |
|---|---|---|
| 제품명 | ⭕⭕ | `goodsNm` — **잘리지 않은 전체 이름**. 축약명은 `abrGoodsNm`에 별도 제공 |
| 가격 | ⭕ | `price` (float) |
| 이미지 | ⭕ | `attFileNm` (절대 URL) |
| 고유 ID | ⭕ | `code` = 바코드. **단 행사상품 응답에는 `code`가 없어** 이미지 URL `GD_<바코드>_001.jpg`에서 추출해야 함 |
| 카테고리 | ⭕ | `departCd.code`(FRESH_FOOD 등), `classCd`, `subclassCd` |
| 기타 | | `isNew`, `ordAppDt`(발주적용일), `goodsStat`(정상/중단) — **`goodsStat`은 단종 판정에 쓸모 있음** |

### 주의사항
- **전체 카탈로그가 아니다.** PB(유어스) + 차별화 상품 + 행사상품만 공개된다.
  일반 매입 상품은 사이트에 목록이 없다. → CU 대비 커버리지가 좁다.
- 행사상품 목록은 "행사에 들어왔다/빠졌다"로도 diff가 튀므로 신상 판정 노이즈가 크다.
  PB(203) + 차별화(584) 787개를 주 대상으로 삼고, 행사는 보조로 두는 편이 안전하다.
- CSRF 토큰은 세션마다 다르다. 매 실행 시 페이지를 먼저 GET할 것.

---

## 3. 세븐일레븐 — MEDIUM

### robots.txt
`https://www.7-eleven.co.kr/robots.txt` → 200. `/product/` 경로는 **허용**.
```
Disallow: /front/, /library/, /management/, /manager/, /upload/, /util/..., /about/marketer/intro.asp
```
⚠️ `/front/`와 `/upload/`가 금지인데 **상품 이미지가 이 경로에 있다**
(`/front/img/product/...`, `/upload/product/8809827/508049.1.jpg`).
→ 이미지 URL을 **참조만** 하는 것은 크롤링이 아니므로 무방하고,
   CLAUDE.md 7장이 이미 이미지 복제 저장을 금지하고 있어 충돌하지 않는다.
   **이미지 파일을 직접 가져오는 동작은 넣지 말 것.**

### 엔드포인트
`/product/7prodList.asp`는 JS로 `presentList.asp`에 POST하는 리다이렉트 껍데기다. 실제 목록은:

```
POST https://www.7-eleven.co.kr/product/listMoreAjax.asp
     intPageSize=100&intCurrPage=2&cateCd1=&cateCd2=&cateCd3=&pTab=2
```
응답: **HTML 조각**. 세션·토큰 불필요.

| pTab | 목록 | 항목 수 |
|---|---|---|
| 1 | 1+1 | 752 |
| 2 | 2+1 | 1,067 |
| 3 | 증정행사 | 2 |
| 4 | 할인행사 | 540 |
| 5 | 7-Select (PB) | 82 |
| 8 | 신상품 | 77 |

Fresh Food는 별도 엔드포인트이고 **한 번에 전부** 받을 수 있다:
```
POST https://www.7-eleven.co.kr/product/dosirakNewMoreAjax.asp
     intPageSize=200&pTab=          ← pTab을 빈 값으로 두면 135건 전부
```

### 페이지네이션 — 규칙이 특이하다
`intCurrPage=1`은 **`intPageSize`를 무시하고 항상 13건**을 반환한다.
2페이지부터 `intPageSize`가 적용되며 오프셋은:

```
offset = 13 + (intCurrPage - 2) × intPageSize     (intCurrPage ≥ 2)
```
실측 검증: size=100,page=2 → 13~113 / size=100,page=3 → 113~213 / size=50,page=3 → 63~113. 일치.

`intPageSize=1067`(전량)은 **읽기 타임아웃**이 났다. 100~200 선을 권장.
→ pTab별로 1 + ceil((total-13)/100) 요청. 전체 약 **35요청**.

전체 수는 목록 페이지 HTML의 `intTotalCount = "1067";` 에서 읽는다.

### 추출 가능 필드
| 필드 | 가능 | 출처 |
|---|---|---|
| 제품명 | ⭕ | `<div class='name'>` / `<span class="tit_product">` |
| 가격 | ⭕ | `<dd class="price_list"><span>` |
| 이미지 | ⚠️ | 상당수가 **플레이스홀더**(`/front/img/product/product_list_01.jpg`). null 처리 필요 |
| 고유 ID | ⚠️ | `fncGoView('072980')` — **6자리 내부 코드, 바코드 아님**. Fresh Food만 이미지 경로에서 바코드 복원 가능(`/upload/product/8809827/508049.1.jpg` → 8809827508049) |
| 카테고리 | ⚠️ | `cateCd1/2/3` 파라미터는 있으나 코드 목록을 이번에 확보하지 못함(`presentListCategoryAjax.asp`로 조회 가능해 보임). pTab을 카테고리 대용으로 쓸 수 있음 |
| 행사 태그 | ⭕ | `ico_tag_07` = 2+1 등 |

### 주의사항
- **전체 카탈로그가 없다.** 행사 탭(1~4, 합 2,361) + PB(82) + 신상품(77)뿐이다.
  행사 탭은 "이번 달 행사"라서 **월초에 대량 교체**된다 → 월 경계에서 diff가 통째로 튄다.
  **이 소스는 diff 방식과 궁합이 나쁘다.** 2주 검증 단계에서 반드시 확인할 것.
- `pTab=8`(신상품)이 존재한다. CLAUDE.md 2.1은 소스의 신상 라벨을 불신하라고 하지만,
  전체 카탈로그가 없는 이상 세븐일레븐만은 예외 처리를 검토해야 할 수 있다.
  → **원칙 변경이 필요하면 코드보다 CLAUDE.md를 먼저 고칠 것.**
- 사이트 전체가 구형 ASP + 인코딩 혼재. 파서를 특히 방어적으로 쓸 것.

---

## 4. 이마트24 — EASY (구조는 가장 단순, 요청 수는 가장 많음)

### robots.txt
`https://www.emart24.co.kr/robots.txt` → 200. 상품 경로 **전면 허용**.
```
Disallow: /founded/brief/req, /founded/recommend    ← 창업 관련. 상품과 무관
```

### 엔드포인트 — XHR이 아니라 **서버 렌더링**
```
GET https://www.emart24.co.kr/goods/pl?page=2
```
HTML에 상품 20개가 이미 들어 있다. XHR 없음. 가장 단순하다.
`www.` 없는 `emart24.co.kr`로 리다이렉트되므로 최종 URL을 따라갈 것.

| 경로 | 목록 | 항목 수 | 페이지 수 |
|---|---|---|---|
| `/goods/event` | 행사 상품 | 2,363 | 119 |
| `/goods/pl` | 차별화(PB) 상품 | 538 | 27 |
| `/goods/ff` | Fresh Food | 178 | 9 |
| | **합계** | **~3,080** | **155** |

`/goods/all`은 **404**다(존재하지 않음).

### 페이지네이션
`?page=N`. 페이지당 **20개 고정** — `pageLength=100`을 넘겨도 서버가 무시하고 20을 유지한다.
전체 수는 HTML 인라인 스크립트의 `const totalCount = "538";`에서 읽는다.
page=1과 page=2 항목이 완전히 다른 것을 확인했다(겹침 0). 마지막 페이지는 20개 미만.

### 추출 가능 필드
| 필드 | 가능 | 출처 |
|---|---|---|
| 제품명 | ⭕ | `.itemtitle > p > a` |
| 가격 | ⭕ | `a.price` ("2,500 원") |
| 이미지 | ⭕ | `.itemSpImg img[src]` (절대 URL) |
| 고유 ID | ⚠️ | **전용 ID 필드가 없다.** 이미지 파일명이 바코드(`.../500x500/5413216993472.JPG`) → 여기서 추출. 실패 시 이름 해시 |
| 카테고리 | ⭕ | `category_seq` 쿼리로 필터 가능. PB 서브브랜드 24종 확인(단독판매 49, 땅스부대찌개 661, MIX:U 622, 성수310 341, 조선호텔 482 등) |
| 신상 라벨 | ⭕ | `<span class="floatL">NEW</span>` — 비신상은 `style="opacity: 0;"`로 숨김 처리. 사용하지 않음 |

### 주의사항
- 상품 상세 링크가 `href="#none"`이다. **`source_url`로 쓸 개별 상품 URL이 없다.**
  → 목록 페이지 URL(`https://www.emart24.co.kr/goods/pl`)로 대체해야 한다.
  CLAUDE.md 7장의 "반드시 요약 + 원문 링크" 요건을 목록 URL로 충족시킬 수 있는지 판단 필요.
- 페이지당 20개 고정이라 요청 수가 155회로 4사 중 가장 많다(그래도 3분 이내).
- 여기도 **전체 카탈로그는 아니다**(행사 + PB + FF).

---

## 종합 판단

### diff 방식과의 궁합
| 소스 | 궁합 | 이유 |
|---|---|---|
| CU | **좋음** | 전 카테고리 카탈로그(5,100), 바코드 ID, 행사와 무관한 상시 목록 |
| GS25 | **보통** | PB·차별화 787개는 안정적. 행사 1,723개는 노이즈 |
| 이마트24 | **보통** | PB 538 + FF 178은 안정적. 행사 2,363개는 노이즈 |
| 세븐일레븐 | **나쁨** | 목록의 91%가 월간 행사 상품. 월 경계에서 전량 교체됨 |

### 고유 ID
- **바코드 확보**: CU(이미지 파일명), GS25 PB(`code` 필드), 이마트24(이미지 파일명), 세븐 FF(이미지 경로)
- **내부 코드만**: 세븐일레븐 일반 목록(6자리) → 소스 내에서는 안정적이나 타 소스와 대조 불가
- **이름 해시 필요**: GS25 행사상품 일부(이미지 URL 파싱 실패 시), 이마트24 이미지 누락 건

### 현 시점 리스크 3가지
1. **CU 외에는 전체 카탈로그가 없다.** CLAUDE.md 2.1의 차집합 전제가 CU에서만 온전히 성립한다.
   나머지 3사는 "행사/PB 목록의 차집합"이 되며 의미가 달라진다.
2. **세븐일레븐의 월간 행사 교체.** 매월 1일 즈음 diff가 수백 건 튈 가능성이 높다.
   CLAUDE.md 2.4의 "70% 감소" 이상 탐지와 별개로 **급증** 탐지도 필요해 보인다.
3. **제품명 절삭·축약.** CU는 12자에서 잘리고, 4사 모두 `샐)`, `혜자)`, `그린)` 같은
   POS 접두사가 붙는다. 소스 간 동일 제품 대조와 LLM 중복 병합이 어려워진다.

### 다음 단계 권고
CLAUDE.md 8장대로 **CU 하나로 수직 관통**하는 것이 맞다. 4사 중 유일하게
전체 카탈로그를 주고, 토큰·세션이 없고, 바코드 ID가 있고, 행사 노이즈가 없다.

---

## 저장된 샘플

```
scratch/samples/
├─ cu_robots.txt                          404 응답 본문
├─ cu_product_page.html                   목록 페이지(폼·카테고리 코드 출처)
├─ cu_productAjax_p1.html                 ★ XHR 응답 40건
├─ cu_product_detail.html                 상세 페이지(이름 절삭 근거)
├─ gs25_robots.txt                        crawl-delay·visit-time
├─ gs25_product_page.html                 CSRF 토큰·엔드포인트 출처
├─ gs25_gscommon.js                       getData() 구현(토큰 전달 방식)
├─ gs25_youus-different-service_page.html
├─ gs25_event-goods_page.html
├─ gs25_freshfood_search.json             ★ JSON 응답(PB)
├─ gs25_differentservice_search.json      ★ JSON 응답(차별화)
├─ gs25_eventgoods_search.json            ★ JSON 응답(행사)
├─ seven_robots.txt
├─ seven_home.html                        상품 경로 목록 출처
├─ seven_prodlist_page.html               리다이렉트 껍데기
├─ seven_presentList_pTab5.html           목록 페이지(intTotalCount 출처)
├─ seven_listMoreAjax_pTab8.html          ★ XHR 응답(신상품)
├─ seven_listMoreAjax_pTab2_size100.html  ★ XHR 응답(2+1, 100건)
├─ seven_freshfood_page.html              galleryArray 인라인 데이터
├─ seven_dosirakNewMoreAjax.html          ★ Fresh Food 135건 일괄
├─ emart24_robots.txt
├─ emart24_goods_all.html                 404 확인용
├─ emart24_goods_event.html               ★ 서버 렌더링 응답(행사)
├─ emart24_goods_pl.html                  ★ 서버 렌더링 응답(PB)
├─ emart24_goods_pl_page2.html            페이지네이션 검증
└─ emart24_goods_ff.html                  ★ 서버 렌더링 응답(FF)
```
