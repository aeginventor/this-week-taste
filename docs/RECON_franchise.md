# 정찰 — 카페 / 디저트 / 프랜차이즈 음식점 (P0 18개 브랜드)

조사일: 2026-08-11
대상: `sources/targets.yml`의 `cafe` / `dessert` / `restaurant` 중 **priority: P0** 전부
방법: curl 직접 요청(User-Agent `ThisWeekTaste/1.0`), 요청 간 1초 이상 간격.
SPA 6곳은 Chrome DevTools 네트워크 로그로 XHR 엔드포인트를 확인했다.
원본 샘플은 `scratch/samples/`.

> **우회 시도 없음.** 403이 뜬 곳에 브라우저 User-Agent를 넣어 재시도하지 않았고,
> robots.txt가 막은 경로는 요청하지 않았다. 막힌 지점은 그대로 HARD로 기록했다.

---

## 요약표

| # | 브랜드 | 채널 | 등급 | (a) 메뉴 목록 | (b) 공지/보도자료 | 가격 | 고유 ID | robots.txt |
|---|---|---|---|---|---|---|---|---|
| 1 | 스타벅스 | cafe | **EASY** | XHR JSON · **1요청 1,179건** | XHR JSON | ❌ 전부 공란 | ⭕ product_CD | 없음(에러페이지) |
| 2 | 투썸플레이스 | cafe | **HARD** | 사이트 전체 403 | 동일 | — | — | 403 |
| 3 | 메가MGC커피 | cafe | **EASY** | GET HTML · 20/page | GET HTML | ❌ | ❌ 이름만 | Allow: / |
| 4 | 컴포즈커피 | cafe | **EASY** | GET HTML · 20/page ×10 | GET HTML | ❌ | ⭕ item_srl | 상품경로 허용 |
| 5 | 이디야커피 | cafe | **HARD**(정책) | `/inc/`가 robots Disallow | ⭕ 허용·서버렌더링 | ❌ | ❌ | `/inc/` 금지 |
| 6 | 파리바게뜨 | dessert | **EASY** | GET HTML 서버렌더링 | GET HTML | ❌ | ⭕ slug | wp-admin만 금지 |
| 7 | 뚜레쥬르 | dessert | **HARD**(정책) | `User-agent: * → Disallow: /` | 동일 | — | — | **전면 금지** |
| 8 | 배스킨라빈스 | dessert | **EASY** | GET HTML 서버렌더링 | GET HTML | ❌ | ⭕ seq | 404(파일 없음) |
| 9 | 던킨 | dessert | **EASY** | Inertia JSON · 12/page | 있음 | ❌ | ⭕ id | Allow: / |
| 10 | 맥도날드 | restaurant | **EASY** | REST JSON | REST JSON | ❌ | ⭕ seq | Allow: / |
| 11 | 버거킹 | restaurant | **MEDIUM** | POST `BKR0632.json` (봉투 미확인) | `/notice/list` | ? | ? | Allow: / |
| 12 | 롯데리아 | restaurant | **HARD**(정책) | 메뉴 경로가 robots Disallow | ⭕ 허용 | — | — | 메뉴 경로 금지 |
| 13 | 맘스터치 | restaurant | **EASY** | GET HTML 서버렌더링 | GET HTML | ❌ | ⭕ go_view | 없음 |
| 14 | BBQ | restaurant | **EASY** | REST JSON | `/events` | ⭕⭕ **있음** | ⭕ id | Allow: / |
| 15 | bhc | restaurant | **EASY** | REST JSON | 있음 | ❌ | ⭕ productCd | Allow: /(주의) |
| 16 | 교촌치킨 | restaurant | **EASY** | GET HTML · **1요청 69건** | GET HTML | ⭕⭕ **있음** | ⭕ id | 제약 없음 |
| 17 | 도미노피자 | restaurant | **EASY** | GET HTML(EUC-KR) | GET HTML | ⭕⭕ **있음** | ⭕ code_01 | /goods/ 허용 |
| 18 | 피자헛 | restaurant | **MEDIUM** | Angular SPA · 메뉴 XHR 미관측 | ? | ? | ? | 404 |

**EASY 12 / MEDIUM 2 / HARD 4.**

HARD 4곳 중 **3곳(이디야·뚜레쥬르·롯데리아)은 기술이 아니라 robots.txt 때문**이다.
기술적으로는 전부 쉬운 사이트다. 투썸만 진짜 봇 차단이다.

---

## 편의점과 결정적으로 다른 점 3가지

편의점 조사(`RECON_convenience.md`)와 비교하면 성격이 완전히 다르다.

**1. 규모가 두 자릿수 작다.** 편의점 4사 합계 13,300건 / 327요청이었는데,
프랜차이즈 14곳(EASY+MEDIUM) 합계는 **약 2,600건 / 약 90요청**이다.
스타벅스 1,179건이 그중 45%다. 나머지 13곳은 브랜드당 30~200건이다.

**2. 가격이 대부분 없다.** 14곳 중 **가격을 주는 곳은 3곳뿐**(BBQ·교촌·도미노 — 전부 배달 주문 기능이 붙은 사이트).
카페·베이커리·버거는 매장별 가격 차이 때문에 웹 메뉴판에 가격을 아예 싣지 않는다.
스타벅스는 `price` 필드가 존재하지만 1,179건 **전부 빈 문자열**이다.
→ `CLAUDE.md` 4장 스키마의 `price`는 이 채널에서 사실상 항상 `null`이다.

**3. 대신 제품 설명문이 공짜로 딸려온다.** 편의점에는 없던 것이다.
스타벅스 `content`, 메가 설명문, 컴포즈, bhc `description`, BBQ `description`,
교촌 `<dd>`, 맘스터치 `<p>`, 배스킨라빈스 해시태그(`#크림치즈 #조청카라멜`).
→ **`curate.py`의 40자 blurb를 LLM이 창작할 필요가 없다.** 공식 설명문을 40자로 줄이는
작업이면 충분하고, 이쪽이 `CLAUDE.md` 6장의 "없는 정보 생성 금지"에도 더 안전하다.

---

## 1. 스타벅스 — EASY ⭐ 이 채널 최고 난도 대비 수확

### robots.txt
`https://www.starbucks.co.kr/robots.txt` → **302 → `/error_page.html`** (파일 없음).
명시적 금지 없음.

### (a) 메뉴 — 전체 카탈로그가 1요청
```
POST https://www.starbucks.co.kr/menu/productListAjax.do
Referer: https://www.starbucks.co.kr/menu/drink_list.do

CATE_CD=0
```
응답: **JSON** `{"list":[...]}` — `CATE_CD=0`이 **전 카테고리 1,179건을 한 번에** 준다.
세션·토큰 불필요.

카테고리별로 받으려면 `CATE_CD`에 아래 W코드를 넣는다
(페이지 인라인 스크립트 `getCateCodeCng()`에서 추출):

| 슬러그 | 코드 | 슬러그 | 코드 |
|---|---|---|---|
| cold_brew | W0000171 | fizzio | W0000061 |
| brewed | W0000060 | tea | W0000075 |
| espresso | W0000003 | juice | W0000062 |
| frappuccino | W0000004 | etc | W0000053 |
| blended | W0000005 | refresher | W0000422 |

> ⚠️ 페이지 JS에 `url = '/upload/json/menu/<코드>.js'` 로 덮어쓰는 줄이 있는데
> 이 경로는 전부 **에러페이지(1,900바이트)**를 반환한다. 죽은 코드다.
> `productListAjax.do`를 그대로 POST할 것.

### 추출 가능 필드
| 필드 | 가능 | 키 |
|---|---|---|
| 제품명 | ⭕ | `product_NM` (절삭 없음, 영문명 `product_ENGNM`) |
| 가격 | ❌ | `price` 존재하나 **1,179건 전부 빈 문자열** |
| 이미지 | ⭕ | `img_UPLOAD_PATH` + `file_PATH` |
| 고유 ID | ⭕ | `product_CD` (13자리, 예: `9200000004544`) |
| 카테고리 | ⭕ | `cate_NAME` |
| 설명 | ⭕⭕ | `content` — 공식 제품 설명문 |
| 영양 | ⭕ | `kcal`, `sugars`, `caffeine`, `protein`, `sodium` … |
| 신상 | ⭕ | `newicon`(Y 71건), `new_SDATE`(예: `20260608`) — 2.1에 따라 판정에는 미사용 |

### ⚠️ 1,179건 중 식음료가 아닌 것이 절반 가까이 섞여 있다
`cate_NAME` 상위: 지역/매장 특화 143, 기타 80, (CF)Crafted Food 65,
청담/별다방 전용상품 49, (CF)샌드위치 47, **일반 S/S 텀블러 40, 일반 머그 36,
시티 머그 & 텀블러 31, 에코백 및 패브릭 제품 21, 일반 글라스 12** …
→ MD(굿즈) 카테고리를 **제외 목록으로 관리**해야 한다. 이 프로젝트는 식음료만 다룬다.

### ⚠️ `product_CD` 중복
1,179건 중 고유 `product_CD`는 **977개**(이름 기준 954개).
같은 상품이 여러 카테고리에 중복 노출된다. **스냅샷 저장 전에 dedup 필요.**

### (b) 새소식
```
POST https://www.starbucks.co.kr/whats_new/newsListAjax.do
pageIndex=1&cate=&searchKeyword=
```
JSON. `seq`, `title`, `reg_dt`, `news_dt`, `cate`(N01~N04), `img_nm`. 10건/page.
실제 목록에 `7월 30일, 복숭아 & 귤 젤리 치즈 케이크 출시`, `치즈 감자 베이글칩 출시`처럼
**출시 공지가 그대로 올라온다.** 다만 MD 출시 공지가 섞인다.

---

## 2. 투썸플레이스 — HARD (봇 차단)

`https://www.twosome.co.kr/` 및 `/robots.txt` 모두 **HTTP 403**.
응답 본문은 CloudFront의 `403 ERROR / The request could not be satisfied / Request blocked.`
robots.txt조차 읽을 수 없어 크롤링 정책 확인이 불가능하다.

**우회 시도하지 않았다.** v1 제외 권고. 대체가 필요하면 `cafe` P1의
할리스·커피빈·파스쿠찌 중에서 승격시키는 편이 낫다.

---

## 3. 메가MGC커피 — EASY

### ⚠️ `targets.yml`의 URL이 틀렸다
`https://www.mgccoffee.com` → **NXDOMAIN** (DNS에 존재하지 않음).
실제 도메인은 **`https://mega-mgccoffee.com`** 이다. targets.yml 수정 필요.

### robots.txt
`Allow: /` 하나뿐. 제약 없음.

### (a) 메뉴
```
GET https://mega-mgccoffee.com/menu/menu.php
    ?page=1&menu_category1=1&menu_category2=1&category=&list_checkbox_all=on
Referer: https://mega-mgccoffee.com/menu/?menu_category1=1&menu_category2=1
```
응답: **HTML 조각**. `<div class="cont_gallery_list_box">` 단위로 20개씩.

> ⚠️ **`list_checkbox_all=on`이 없으면 0건이 온다.** 빈 값·생략 모두 366바이트 빈 껍데기.
> 이 한 글자가 함정이다.

| menu_category1 | 페이지 수 | 대략 건수 |
|---|---|---|
| 1 | 9 | ~170 |
| 2 | 2 | ~30 |
| 3 | 2 | ~30 |
| **합계** | **13요청** | **~230** |

추출: 이름(`<b>`), 영문명, 설명문, 이미지(`img.79plus.co.kr` 절대 URL), `ICE`/`HOT` 라벨.
**가격 없음. 상품 고유 ID 없음** → 이름 해시 필요.

### (b) 공지 / 이벤트
```
GET https://mega-mgccoffee.com/bbs/?bbs_category=1   # 공지사항 (서버렌더링, 39행)
GET https://mega-mgccoffee.com/bbs/?bbs_category=3   # 이벤트 (서버렌더링, 12건 갤러리형)
```
상세 링크가 **base64 인코딩된 쿼리스트링**이다:
`/bbs/detail/?YmJzX2lkeD02NTUm...` → `bbs_idx=655&bbs_category=3&bbs_detail_category=&bbs_page=1`

---

## 4. 컴포즈커피 — EASY

Rhymix CMS. 루트(`composecoffee.com/`)는 스플래시 페이지이고 실제 콘텐츠는 `/index1`.

### robots.txt
`Allow:/` + 게시판 일부 경로만 Disallow. 메뉴 경로는 허용.

### (a) 메뉴 — 서버 렌더링
```
GET https://composecoffee.com/index.php?mid=compose&act=dispCafemenuGalleryList&page=N
```
페이지당 **20개 고정**, **10페이지 = 약 200건**. 카테고리별로 좁히려면 `&category_srl=`:

| 카테고리 | category_srl | 카테고리 | category_srl |
|---|---|---|---|
| 추천메뉴 | 301298 | 에이드ㆍ주스 | 303368 |
| 커피ㆍ콜드브루 | 303364 | 티 | 303369 |
| 베버리지 | 303365 | 푸드ㆍ디저트 | 308857 |
| 프라페ㆍ스무디 | 303366 | 아이스크림 | 303371 |
| 밀크쉐이크 | 303367 | | |

(페이지의 `<select>` 옵션값에서 확인. `308857`만 번호대가 튄다 — 나중에 추가된 카테고리로 보인다.)

추출: 이름(`.cafemenu-menu-name`), 이미지, **`item_srl` = 고유 ID**(예: 318635).
가격 없음.

### (b) 뉴스 / 이벤트
`https://composecoffee.com/news/<id>`, `https://composecoffee.com/event/<id>`.
Rhymix 표준 게시판이라 목록 페이지도 서버 렌더링이다.

---

## 5. 이디야커피 — HARD (robots.txt가 막는다)

### robots.txt
```
User-agent:*
Disallow:/admin/
Disallow:/manager/
Disallow:/member/
Disallow:/inc/          ← 이게 문제다
Disallow:/checkplus/
```

### (a) 메뉴 — 접근 경로가 금지 구역 안에만 있다
`/contents/drink.html`은 허용 경로이지만, **HTML에 상품이 하나도 없다.**
목록은 전부 아래 XHR로 채워진다:
```
GET /inc/ajax_brand.php?gubun=menu_more&product_cate=7&chked_val=&skeyword=
GET /inc/ajax_brand.php?product_cate=7&gubun=slide_detail&no=<id>
```
`/inc/`는 robots.txt Disallow. **`CLAUDE.md` 5장(robots.txt 존중)에 따라 호출하지 않았다.**
Playwright로 페이지를 렌더링해도 결국 같은 금지 경로를 때리게 되므로 MEDIUM이 아니라 HARD다.

### (b) 공지 — 여긴 허용이고 서버 렌더링이다
```
GET https://www.ediya.com/contents/notice.html?tb_name=notice
```
14건 서버 렌더링. 다만 실제 내용은 `즉석 팝콘 도입 매장 리스트`, `일부 메뉴 가격 조정 안내`처럼
**운영 공지 위주라 신메뉴 소식이 거의 없다.**
보도자료 게시판(`/C/contents/notice.html?tb_name=cnews`)은 **최신 글이 2020년**으로 사실상 방치 상태다.

**판정: 메뉴 자동화 불가, 공지도 실익 없음. v1 제외 권고.**

---

## 6. 파리바게뜨 — EASY

WordPress 기반. robots.txt는 `/wp-admin/`만 금지.

### (a) 메뉴 — 완전 서버 렌더링
```
GET https://www.paris.co.kr/products/
GET https://www.paris.co.kr/products/?cat1=브레드
```
카테고리 8종: 브레드 / 케이크 / 디저트-스낵 / 샌드위치-샐러드 / 커피-음료 /
퍼스트클래스키친 / 선물.
각 카테고리 블록에 **`<ul data-total-count="45">`** 로 전체 건수가 박혀 있다.
`/products/` 한 장에 56개 상품이 이미 들어 있다.

추출:
| 필드 | 출처 |
|---|---|
| 제품명 | `h3.product-name` |
| 이미지 | `img.product-tb` (CloudFront 절대 URL) |
| 고유 ID | 상세 URL 슬러그 `/product/red-bean-soboro-bread/` |
| 가격 | ❌ 없음 |

> ⚠️ 슬러그가 **한글 퍼센트 인코딩인 경우가 섞여 있다**
> (`/product/%ed%95%ab%eb%8f%84%ea%b7%b8%eb%8f%84%eb%84%9b/` = 핫도그도넛).
> ID로 쓸 때 디코딩 후 정규화할 것.

### (b) 공지
`https://www.paris.co.kr/notice/` 서버 렌더링. `<h3>` 단위.
다만 `[공지사항] 해피포인트 적립률 변경` 류의 운영 공지가 대부분이다.

---

## 7. 뚜레쥬르 — HARD (robots.txt 전면 금지)

```
## disallow all other bots
User-agent: *
Disallow: /

## Google
User-agent: Googlebot
Allow: /$
Allow: /bread
Allow: /product
...
```
Googlebot / Googlebot-Mobile / Googlebot-image / NaverBot / Yeti / Bingbot **6종만**
개별 허용하고, 그 외 모든 User-Agent에 대해 사이트 전체를 금지한다.

우리 크롤러는 `Disallow: /` 대상이다. **사이트 요청을 아예 하지 않았다.**
(robots.txt 자체는 읽었다 — 이건 robots.txt 취득이라 금지 대상이 아니다.)

**판정: v1 제외.** 검색엔진 봇 UA를 사칭하는 건 명백한 우회이므로 검토 대상이 아니다.
파리바게뜨(허용)로 베이커리 채널을 커버하고, 필요하면 dessert P1의
크리스피크림·설빙을 승격시키는 쪽을 권고한다.

---

## 8. 배스킨라빈스 — EASY

### robots.txt
`https://www.baskinrobbins.co.kr/robots.txt` → **HTTP 404**(파일 없음). 금지 규칙 없음.

### (a) 메뉴 — 서버 렌더링
```
GET https://www.baskinrobbins.co.kr/menu/list.php?category=A   # 아이스크림 (31건)
GET .../menu/list.php?category=F                                # 프리팩
GET .../menu/list.php?category=B                                # 아이스크림 케이크
GET .../menu/list.php?category=E                                # 디저트
GET .../menu/list_subcategory.php?category=C                    # (서브카테고리형)
GET .../menu/list_subcategory.php?category=D                    # (서브카테고리형)
GET .../menu/fom.php                                            # 이달의 맛
```
7요청이면 전 카탈로그. 페이지네이션 없음.

추출:
| 필드 | 출처 |
|---|---|
| 제품명 | `strong.menu-list__title` |
| 이미지 | `img.menu-list__image` |
| 고유 ID | `view.php?seq=1124` |
| 태그 | `span.menu-list__hash` → `#크림치즈 #조청카라멜 #현미그라함쿠키` |
| 신상 | `li.menu-list__item--new` (2.1에 따라 판정에는 미사용) |
| 가격 | ❌ |

> `menu-list__hash`는 **`CLAUDE.md` 4장의 `tags` 필드를 LLM 없이 그대로 채울 수 있다.**
> 이 채널에서 유일하게 태그가 소스에 이미 존재하는 브랜드다.

> 제품명에 HTML 엔티티가 그대로 들어있다: `&#40;Lessly Edition&#41; 바 베 바`.
> 파서에서 `html.unescape()` 필수.

### (b) 보도자료 / 공지
```
GET /information-center/press/list.php     # 보도자료 (10행/page)
GET /information-center/notice/list.php    # 공지사항
```
`table.board-list__table-list` 서버 렌더링. 신제품 출시 보도자료가 여기 올라온다.

---

## 9. 던킨 — EASY

Laravel + **Inertia.js(React)**. robots.txt는 `Allow: /`.

### (a) 메뉴 — HTML 안에 JSON이 통째로 들어있다
Inertia는 페이지 데이터를 `<div id="app" data-page="{...}">` 속성에 실어 보낸다.
즉 **HTML을 받아 `data-page`를 `html.unescape()` → `json.loads()` 하면 끝**이다.

```
GET https://www.dunkindonuts.co.kr/menu?cat=1&page=1
```
더 깔끔하게, `X-Inertia: true` + `X-Inertia-Version: <version>` 헤더를 붙이면
**순수 JSON**(`Content-Type: application/json`)이 온다. version 값은 같은 `data-page`의 `version` 키.

| cat | 이름 | 전체 | 페이지(12/page) |
|---|---|---|---|
| 1 | DONUT | 88 | 8 |
| 2 | FOOD | — | — |
| 3 | COFFEE | — | — |
| 5 | BEVERAGE | — | — |
| 6 | SNACK & MORE | — | (`productCats` 서브카테고리형) |

전체 수는 `props.products.meta.total`, 마지막 페이지는 `meta.last_page`.
`/menu/all` 은 카테고리당 4건 미리보기라 **스냅샷용으로 쓰면 안 된다.**

추출 (`props.products.data[]`):
| 필드 | 키 |
|---|---|
| 제품명 | `TITLE` / 영문 `E_TITLE` |
| 이미지 | `MAIN_IMG_FILE` (상대경로, 호스트 붙일 것) |
| 고유 ID | `id` (예: 536) |
| 카테고리 | `PRODUCT_CAT1_NM`, `PRODUCT_CAT2_NM` |
| 기타 | `SEASON_MENU_DIV`, `LOWSUGAR_DIV`, `TOP_YN` |
| 가격 | ❌ |

### (b) 뉴스
`https://www.dunkindonuts.co.kr/brand/news/list` — 같은 Inertia 구조.
단, 파라미터 없이 호출하면 `props`에 `categories`만 오고 목록이 비어 있다. 카테고리 지정 필요.

---

## 10. 맥도날드 — EASY (이 채널에서 가장 깔끔한 REST)

Nuxt SPA. `window.__NUXT__.config.public.apiBase = "https://www.mcdonalds.co.kr/api/v1"`.
robots.txt는 `Allow: /`.

### (a) 메뉴
```
GET https://www.mcdonalds.co.kr/api/v1/kor/category/list
GET https://www.mcdonalds.co.kr/api/v1/kor/product/product/list
    ?page=1&view_rows=500&mainCategory=1&subCategory=16&searchWord=
```
JSON, 인증 없음. `view_rows`를 500까지 올려도 서버가 존중한다.
응답 봉투는 `{"resultCode":100, "resultObject":{"totalCount":N, "mainCategory":[], "subCategory":[], "list":[]}}`.

카테고리 7종: 버거(1) / 맥런치(7) / 해피 스낵(8) / 사이드&디저트(4) /
맥모닝(2) / 해피밀(3) / 맥카페&음료(5).
`subCategory`는 `category/list`에는 비어 오고, `product/list` 응답의 `subCategory` 키에 들어있다
(예: 버거 → `seq=16` "버거전체").

> ⚠️ `mainCategory=&subCategory=` 를 비워도 전체가 오지 않는다(직전 조합 결과와 동일하게 나옴).
> 카테고리별로 순회할 것. 약 7~15요청.

추출 (`resultObject.list[]`):
| 필드 | 키 |
|---|---|
| 제품명 | `korName` / `engName` |
| 설명 | `korContent` (HTML `<br>` 포함) |
| 이미지 | `pcImageUrl`, `moImageUrl` (상대경로) |
| 고유 ID | `seq` (예: 833) |
| 카테고리 | `categoryName`, `subCategoryName` |
| 영양 | `calorie`, `protein`, `sodium`, `caffeine` … |
| 신상 | `newIcon` |
| 가격 | ❌ **필드 자체가 없다** |

`regDate` 포맷이 `"2026-August-4th"` 라는 기괴한 형태다. 파싱하지 말고 무시할 것
(신상 판정은 2.1의 차집합으로 한다).

### (b) 보도자료
```
GET https://www.mcdonalds.co.kr/api/v1/kor/press/list?page=1&view_rows=20   # 42건
GET https://www.mcdonalds.co.kr/api/v1/kor/news/list?page=1&view_rows=20    # 3건(운영 공지)
```
> ⚠️ `press/list`는 **응답이 3.2MB**다. 목록 API인데 본문 HTML을 통째로 실어 보낸다.
> `view_rows`를 작게 유지할 것.

---

## 11. 버거킹 — MEDIUM

Vue SPA + **bizMOB** 프레임워크(`bizMOB-core.js`, `bizMOB-xross4.js`).
robots.txt는 `Allow: /`.

### 확인한 것
Vue Router 경로(`/js/app.js`에서 추출):
`/menu/main`, `/menu/detail/:menuCd?`, `/notice/list`, `/notice/:idNotice?`,
`/event/ongoing`, `/event/detail/:eventId?`, `/store/all` …

`/menu/main` 진입 시 실제로 발생하는 XHR:
```
POST https://www.burgerking.co.kr/burgerking/BKR0632.json
POST https://www.burgerking.co.kr/burgerking/BKR0633.json
```
(홈은 `BKR0220.json`, `BKR0113.json`)

### 막힌 지점
빈 body(`{}`)로 POST하면 **HTTP 400 Bad Request**가 온다.
bizMOB은 고유한 요청 봉투(header/body 래핑)를 쓰는데, 그 형태를 이번 조사에서 확정하지 못했다.
DevTools 네트워크 로그는 요청 **본문**까지는 보여주지 않았다.

**다음 단계**: 브라우저에서 `/menu/main`을 열고 `BKR0632.json` 요청의 Payload 탭을 한 번만
캡처하면 EASY로 내려온다. 봉투만 알면 그 뒤는 순수 JSON POST다.
그때까지는 Playwright 대상(MEDIUM)으로 둔다.

---

## 12. 롯데리아 — HARD (메뉴 경로가 robots.txt Disallow)

### robots.txt (`https://www.lotteeatz.com/robots.txt`)
```
User-agent: *
Allow:/
Disallow:/hsv/products/*/*/menu/
Disallow:/qsv/products/*/*/menu/
```
**하필 금지된 두 패턴이 메뉴 페이지 경로다.** 홈페이지(1.7MB)에 등장하는 상품 관련 경로는
`/hsv/products/`, `/qsv/products/` 뿐이고, 실제 메뉴는 그 아래 `*/*/menu/` 로 내려간다
(`/qsv/products/` 단독 호출은 404).

`CLAUDE.md` 5장에 따라 해당 경로는 요청하지 않았다.

### 허용되는 것
```
GET https://www.lotteeatz.com/board/notice    # 200, 407KB
```
공지 게시판은 금지 대상이 아니다. 다만 롯데리아·엔제리너스·크리스피크림을 아우르는
롯데GRS 통합 사이트라 브랜드 구분이 필요하다.

**판정: 메뉴 스냅샷 불가.** 공지 기반 보조 트랙으로만 검토.
버거 채널은 맥도날드·맘스터치(둘 다 EASY)로 커버하고,
`restaurant` P1의 KFC·노브랜드버거 승격을 검토할 것.

---

## 13. 맘스터치 — EASY

### 진입 경로가 두 단계다
`https://www.momstouch.co.kr/` 는 인트로 스플래시이고, 실제 사이트는 **`/home.php`** 다
(스플래시가 `location.href='/home.php'`로 넘긴다).
robots.txt는 없다(홈으로 리다이렉트).

### (a) 메뉴 — 순수 서버 렌더링, XHR 없음
```
GET https://momstouch.co.kr/menu/new.php?s_sect1=CG0001
```
브라우저 네트워크 로그로 확인한 결과 **XHR이 단 한 건도 발생하지 않는다.** HTML이 전부다.

| s_sect1 | 카테고리 |
|---|---|
| `new` | New! |
| CG0045 | 또잇 |
| CG0005 | 버거 |
| CG0004 | 치킨 |
| CG0003 | 맘스세트 |
| CG0002 | 사이드 |
| CG0001 | 음료 |
| CG0046 | 피자 |

8요청이면 전체. 추출:
| 필드 | 출처 |
|---|---|
| 제품명 | `<h3><span>Cider</span>사이다</h3>` — **영문명이 `<span>`, 한글명이 그 뒤 텍스트** |
| 부제 | `p.sub-text` ("톡 쏘는 사이다") |
| 설명 | `<p>` (`<br />` 포함) |
| 이미지 | `figure > span[style]`의 `background-image: url('/upload_file/product_info/...')` — **`src`가 아니라 인라인 CSS** |
| 고유 ID | `href="javascript:go_view('5');"` |
| 가격 | ❌ |

이미지가 CSS `background-image`라 일반 `<img src>` 파서로는 못 잡는다. 주의.

### (b) 공지
`https://momstouch.co.kr/brand/notice-list.php` 서버 렌더링.

---

## 14. BBQ — EASY ⭐ 이 채널에서 유일하게 가격·영양·원산지까지 다 준다

Next.js SPA지만 **API가 같은 도메인에 노출되어 있고 인증이 없다.**
robots.txt는 `Allow: /`.

### (a) 메뉴
```
GET https://bbq.co.kr/api/delivery/menu/category
GET https://bbq.co.kr/api/delivery/menu/{categoryId}
```
응답은 **최상위 배열**(봉투 없음).

카테고리: 필릭스 PICK(34), 추천(17), 세트(18), 사이드, 음료 등.
카테고리 수가 10개 내외라 **약 11요청**이면 전 카탈로그.

추출:
| 필드 | 키 |
|---|---|
| 제품명 | `menuName` (예: `황금올리브치킨™`) |
| **가격** | **`menuPrice`** (정수, 예: 23000) + `addPrice`, `displayPrice` |
| 설명 | `description` |
| 이미지 | `menuImageUrl` (절대 URL) |
| 고유 ID | `id` (예: 3003) |
| 영양 | `nutrient.{calorie,sugars,protein,saturatedFat,natrium}` |
| 알레르기 | `allergy` |
| 원산지 | `origin[]` |
| 상태 | `isSoldOut`, `canDeliver`, `canTakeout`, `isAdultOnly` |

> `menuName`에 `™`, `®` 같은 기호가 들어간다. 제품 동일성 판정 시 정규화 대상이다.

### (b) 이벤트
`https://bbq.co.kr/events` (SPA). 보도자료 전용 페이지는 확인하지 못했다.

---

## 15. bhc — EASY

Next.js App Router. 메뉴 데이터는 RSC 페이로드에 없고 클라이언트에서 REST를 친다.

### robots.txt — 읽을 것이 있다
```
User-agent: *
Content-Signal: search=yes, ai-train=no, use=reference
Allow: /

User-agent: ClaudeBot     → Disallow: /
User-agent: GPTBot        → Disallow: /
User-agent: CCBot         → Disallow: /
User-agent: Google-Extended, Amazonbot, Bytespider, meta-externalagent … → Disallow: /
```
우리 크롤러 UA는 `ThisWeekTaste/1.0`이므로 `User-agent: *` 그룹에 해당하고 **허용**이다.
`ClaudeBot`은 Anthropic의 웹 크롤러 UA이지 우리 스크래퍼가 아니다.

> ⚠️ 다만 `Content-Signal`에 `ai-train=no, use=reference`가 명시되어 있다.
> 우리 용도는 **요약 + 원문 링크(reference)**이고, 이는 `CLAUDE.md` 7장이 이미 강제하는 형태와 일치한다.
> 수집한 데이터를 학습에 쓰지 않는다는 전제가 깨지면 이 소스는 재검토 대상이다.
> **스크래퍼 UA에 `ClaudeBot`이나 `Claude` 문자열을 넣지 말 것** — 넣는 순간 Disallow 그룹이 된다.

### (a) 메뉴
```
GET https://www.bhc.co.kr/api/v1/web/categories/{id}/products
```
카테고리 ID는 `/menu/{id}` 페이지에서 확인: **1, 23, 47, 50, 74** (5요청).
(`/api/v1/web/categories` 목록 엔드포인트는 404 — 카테고리 ID는 메뉴 페이지 HTML에서 긁어야 한다.)

응답 봉투: `{"status":"success","code":200,"body":[...]}`

추출 (`body[]`):
| 필드 | 키 |
|---|---|
| 제품명 | `productNm` |
| 설명 | `description` (`mobileListDescription` 등 3종) |
| 이미지 | `mainImg` (절대 URL) |
| 고유 ID | `productCd` (예: `65000`) |
| 카테고리 | `cateNm[]` (배열), `cateSortList[].sortKey` |
| 플래그 | `isNew`, `isBest`, `isLimited` |
| 가격 | ❌ (`options[]`에 들어있을 가능성 — 이번 샘플은 전부 빈 배열) |

---

## 16. 교촌치킨 — EASY ⭐ 1요청에 69건, 가격까지

### robots.txt
```
User-agent: Yeti
Allow: /
```
**`User-agent: *` 그룹이 아예 없다.** 우리에게 적용될 규칙이 없으므로 허용으로 간주.

`https://www.kyochon.com/` 은 meta refresh로 `/main/`으로 넘긴다.

### (a) 메뉴 — 탭이 전부 한 HTML에 들어있다
```
GET https://www.kyochon.com/menu/chicken.asp
```
`?code=1..21` 로 시리즈별 필터가 되지만, **파라미터 없이 부르면 69건이 전부 온다.**
`/menu/burger.asp` 등 다른 카테고리도 동일 구조.

추출:
| 필드 | 출처 |
|---|---|
| 제품명 | `dl.txt > dt` |
| 설명 | `dl.txt > dd` (원육 수급 안내 등 주석 포함) |
| **가격** | **`p.money > strong`** (예: `23,000` — "권장소비자가격") |
| 이미지 | `p.img > img` (`/uploadFiles/TB_ITEM/...`) |
| 고유 ID | `view.asp?id=41363&cg=2` |

### (b) 공지
`https://www.kyochon.com/cs/notice.asp` — 서버 렌더링(`notice_view.asp?seq=790`).
다만 실제 내용은 `서비스 이용약관 개정 안내`, `개인정보처리방침 개정` 류로
**신제품 소식이 없다.** 메뉴 diff에만 의존하는 편이 낫다.

---

## 17. 도미노피자 — EASY (단, EUC-KR)

### robots.txt (`https://web.dominos.co.kr/robots.txt`)
```
Allow: /goods/    ← 상품
Allow: /bbs/      ← 게시판
Allow: /event/, /contents/, /company/ …
Disallow: /order/, /mypage/, /member/, /test/
```
상품과 게시판 모두 **명시적 허용**. 크롤 딜레이 지정 없음.

`https://www.dominos.co.kr/` → `web.dominos.co.kr/gate` → `/main` 2단 리다이렉트.

### ⚠️ 인코딩이 EUC-KR이다
`Content-Type: text/html; charset=euc-kr`. robots.txt도 `text/plain;charset=euc-kr`.
`response.text`를 그냥 쓰면 전부 깨진다. **`.decode('euc-kr')` 명시 필수.**
이 채널 18곳 중 유일하다.

### (a) 메뉴
```
GET https://web.dominos.co.kr/goods/list?dsp_ctgr=C0101
```
서버 렌더링. 확인된 카테고리 코드: `C0101`(피자), `C0201`, `C0202`.
전체 카테고리 코드 목록은 `/main` 네비게이션에서 추가로 긁어야 한다.

추출:
| 필드 | 출처 |
|---|---|
| 제품명 | `div.subject` |
| **가격** | **`div.price-box > span.price`** — L/M 사이즈별 (`L 28,900원~ / M 21,500원~`) |
| 이미지 | `img[data-src]` (lazyload — **`src`는 플레이스홀더 `bg.gif`**) |
| 고유 ID | `code_01=RPZ001SL` (상세 URL `/goods/detail?dsp_ctgr=C0101&code_01=...&dough_gb=203`) |
| 태그 | `div.hashtag` (`#누구나 사랑하는 베이직 피자`) |

> 가격이 `~`(부터) 표기라 정수 파싱 시 주의. 도우/사이즈 조합에 따라 달라진다.
> `CLAUDE.md` 4장의 `price`(정수)에 넣으려면 **M 사이즈 최저가**로 정규화하는 규칙이 필요하다.

### (b) 보도자료
```
GET https://web.dominos.co.kr/bbs/newsList?type=P   # 보도자료
GET https://web.dominos.co.kr/bbs/newsList?type=N   # 뉴스
```
목록은 form POST + `goView(idx)` → `/bbs/newsView?idx=<idx>` 구조. 서버 렌더링.

---

## 18. 피자헛 — MEDIUM

Angular SPA(`/static/web/runtime.js`, `polyfills-es5.js`).
`https://www.pizzahut.co.kr/robots.txt` → **HTTP 404**(파일 없음).

### 막힌 지점
`/menu`, `/menu/pizza`, `/menu/pizza/premium`, `/menu/side` 를 curl로 받으면
**전부 홈페이지와 동일한 13,109바이트 SPA 껍데기**다.

브라우저로 각 메뉴 URL을 직접 로드하고 네트워크를 관찰했으나,
**상품 관련 XHR이 한 건도 관측되지 않았다**(GA·광고 픽셀만 발생).
`/menu/pizza`는 자동으로 `/menu/pizza/best`로 리다이렉트된다.

추정 원인: 피자헛은 메뉴 조회 전에 **주문 방식(배달/방문포장)과 매장 선택**을 요구하고,
그 상태가 정해져야 메뉴 API를 호출한다. 초기 부트스트랩 때 받은 데이터를
클라이언트에 캐시해 두는 것으로 보인다.

**다음 단계**: 브라우저에서 배달/포장 선택 → 매장 지정까지 진행한 뒤 네트워크를 다시 캡처.
그때까지 MEDIUM(Playwright 필요)으로 둔다.
같은 pizza 채널의 도미노가 EASY이므로 우선순위는 낮다.

---

## 종합 판단

### 요청 수 / 소요 시간 추정 (EASY 12곳)

| 브랜드 | 요청 | 건수 |
|---|---|---|
| 스타벅스 | 1 (+뉴스 1) | 1,179 (MD 제외 시 ~700) |
| 메가MGC | 13 | ~230 |
| 컴포즈 | 10 | ~200 |
| 파리바게뜨 | 8 | ~250 |
| 배스킨라빈스 | 7 | ~150 |
| 던킨 | ~25 | ~300 |
| 맥도날드 | ~9 | ~150 |
| 맘스터치 | 8 | ~100 |
| BBQ | ~11 | ~120 |
| bhc | 5 | ~120 |
| 교촌 | 2 | ~90 |
| 도미노 | ~6 | ~80 |
| **합계** | **~105** | **~2,970** |

1초 간격이면 **약 2분**. 편의점(327요청·6분)과 합쳐도 주간 스냅샷 1회에 10분 이내다.

### diff 방식과의 궁합 — 편의점보다 훨씬 좋다

| 소스 | 궁합 | 이유 |
|---|---|---|
| 스타벅스 | **좋음** | 전체 카탈로그, 고유 ID, 시즌 음료 교체가 뚜렷 |
| 배스킨라빈스 | **좋음** | '이달의 맛'이 매달 바뀌는 구조. diff가 정확히 잡아낸다 |
| 던킨 / bhc / BBQ / 맥도날드 | **좋음** | 전체 메뉴판이 API로 그대로 노출. 행사 노이즈 없음 |
| 교촌 / 도미노 / 맘스터치 | **좋음** | 메뉴 수가 적고 상시 메뉴 위주라 변동이 곧 신메뉴 |
| 파리바게뜨 | **보통** | 카탈로그가 크고 시즌 상품 회전이 빨라 diff 건수가 많을 수 있음 |
| 메가MGC / 컴포즈 | **주의** | **고유 ID가 없다.** 이름 해시에 전적으로 의존 |

**편의점의 최대 약점(행사 상품이 목록의 대부분이라 월 경계에서 전량 교체)이 여기엔 없다.**
프랜차이즈는 전부 상시 메뉴판이다. `CLAUDE.md` 2.1의 차집합 전제가 이 채널에서 훨씬 잘 성립한다.

### 고유 ID 확보 현황

- **자체 ID 있음(10곳)**: 스타벅스 `product_CD`, 컴포즈 `item_srl`, 파리바게뜨 슬러그,
  배스킨라빈스 `seq`, 던킨 `id`, 맥도날드 `seq`, 맘스터치 `go_view`,
  BBQ `id`, bhc `productCd`, 교촌 `id`, 도미노 `code_01`
- **이름 해시 필요(2곳)**: **메가MGC, 컴포즈 일부**
- **주의**: 이 ID들은 전부 **브랜드 내부 코드**다. 편의점처럼 바코드가 아니므로
  **소스 간 동일 제품 대조는 불가능하다.** 프랜차이즈 메뉴는 애초에 브랜드 전용이라 문제되지 않는다.

### 현 시점 리스크 3가지

1. **가격이 없다는 사실이 스키마에 반영되어야 한다.**
   14곳 중 11곳이 `price`를 주지 않는다. `CLAUDE.md` 4장은 `price`를 "미상이면 null"로
   허용하지만, 이 채널에서는 null이 예외가 아니라 **기본값**이다.
   웹 UI가 가격을 전제로 설계되면 프랜차이즈 카드가 전부 비어 보인다.
   → 발행 스키마에 `price_available: false` 같은 채널 단위 표시를 두거나,
   UI에서 가격 없는 채널을 다르게 렌더링하는 결정이 필요하다.

2. **HARD 4곳 중 3곳이 robots.txt 때문이다** (뚜레쥬르·이디야·롯데리아).
   기술적으로는 전부 30분이면 붙일 수 있는 사이트인데 정책상 못 한다.
   P0 24개 중 3개가 이 사유로 빠지므로, `targets.yml` 하단의 "P0 중 HARD 판정이 나오면
   P1에서 승격" 규칙을 실제로 적용해야 한다.
   승격 후보: 크리스피크림(dessert P1), KFC·노브랜드버거(restaurant P1), 할리스·커피빈(cafe P1).

3. **메가MGC·컴포즈는 고유 ID가 없어 이름 해시에 100% 의존한다.**
   그런데 이 두 브랜드는 메뉴명 변경이 잦은 편이다(시즌 접두사 `[여름한정]` 등).
   이름이 한 글자만 바뀌어도 "단종 1건 + 신상 1건"으로 잘못 잡힌다.
   → `diff.py`의 동일성 판정에서 **정규화 규칙(대괄호 접두사 제거, 공백/특수문자 정리) 후
   유사도 비교**가 필요하다. 이건 편의점의 POS 접두사(`샐)`, `혜자)`) 문제와 같은 뿌리다.

### 다음 단계 권고

`CLAUDE.md` 8장의 순서(CU 하나로 수직 관통 → 2주 검증)를 그대로 지킨다.
프랜차이즈는 4단계 "확장"에서 붙이되, 순서는 이렇게 권고한다:

1. **스타벅스** — 1요청에 1,179건. 투입 대비 수확이 압도적이다. (단 MD 필터링 먼저)
2. **맥도날드 · BBQ · bhc** — 깔끔한 REST 3종. 파서가 거의 같은 모양이 된다.
3. **교촌 · 도미노 · 맘스터치 · 배스킨라빈스** — HTML 파서 4종.
4. **던킨 · 파리바게뜨 · 컴포즈 · 메가** — 나머지.

> `CLAUDE.md` 7장의 "소스 3개까지는 복붙, 4개째에 공통화" 규칙에 따르면
> 2번 그룹(REST 3종)을 붙이는 시점에 공통화 압력이 온다.
> 편의점 4사와 합치면 이미 4개를 넘으므로, **프랜차이즈 착수 전에 `scrapers/base.py` 정리가 선행**되어야 한다.

---

## 저장된 샘플

```
scratch/samples/
├─ [카페]
│   ├─ starbucks_robots.txt                    302 → 에러페이지 (robots 없음 근거)
│   ├─ starbucks_menu_drink_list.html          CATE_CD 매핑·엔드포인트 출처
│   ├─ starbucks_productListAjax_all.json      ★ CATE_CD=0 전 카탈로그 1,179건
│   ├─ starbucks_productListAjax_coldbrew.json 카테고리별 응답 24건
│   ├─ starbucks_newsList_v2.js                뉴스 XHR 엔드포인트 출처
│   ├─ starbucks_newsListAjax.json             ★ 새소식 JSON
│   ├─ twosome_robots.txt / twosome_403.html   403 차단 근거
│   ├─ mega_robots.txt / mega_home.html
│   ├─ mega_menu.html                          menu.php 파라미터 출처
│   ├─ mega_menu_php_c1~c3.html                ★ XHR 응답 20건씩
│   ├─ mega_bbs_cat1.html / mega_bbs_cat3.html 공지·이벤트
│   ├─ compose_home.html / compose_index1.html 스플래시 구조
│   ├─ compose_menu_gallery.html               ★ 서버렌더링 20건 + category_srl
│   ├─ compose_menu_gallery_p2.html            페이지네이션 검증
│   ├─ ediya_robots.txt                        ★ /inc/ Disallow 근거
│   ├─ ediya_drink.html                        ajax_brand.php 호출 근거
│   ├─ ediya_notice.html / ediya_cnews.html    공지(유효)·보도자료(2020년 정지)
│   └─ ediya_sitemap.xml
├─ [디저트]
│   ├─ parisbaguette_robots.txt
│   ├─ parisbaguette_products.html             ★ 서버렌더링 56건 + data-total-count
│   ├─ parisbaguette_notice.html
│   ├─ tourlesjours_robots.txt                 ★ Disallow: / 전면 금지 근거
│   ├─ baskinrobbins_robots.txt                404 응답 본문
│   ├─ baskinrobbins_menu_A.html               ★ 서버렌더링 31건 + seq + 해시태그
│   ├─ baskinrobbins_press.html                보도자료 board-list
│   ├─ baskinrobbins_notice.html
│   ├─ dunkin_robots.txt
│   ├─ dunkin_menu_all.html                    카테고리당 4건 미리보기(사용 금지 근거)
│   ├─ dunkin_menu_cat1~cat6.html              ★ data-page JSON, cat1=88건/8페이지
│   ├─ dunkin_menu_cat1_inertia.json           ★ X-Inertia 순수 JSON 응답
│   └─ dunkin_news_list.html
├─ [음식점]
│   ├─ mcdonalds_robots.txt
│   ├─ mcdonalds_menu_burger.html              apiBase 출처
│   ├─ mcdonalds_api_category_list.json        ★ 카테고리 7종
│   ├─ mcdonalds_api_product_list.json         ★ 상품 22건 + 전체 필드
│   ├─ burgerking_robots.txt / burgerking_home.html
│   ├─ burgerking_BKR0632.json                 400 응답(봉투 미확인 근거)
│   ├─ burgerking_BKR0633.json                 400 응답
│   ├─ lotteria_robots.txt                     ★ 메뉴 경로 Disallow 근거
│   ├─ lotteria_home.html / lotteria_products.html / lotteria_notice.html
│   ├─ momstouch_robots.txt                    robots 없음(홈으로 리다이렉트)
│   ├─ momstouch_homephp.html                  s_sect1 코드 출처
│   ├─ momstouch_menu_CG0001.html              ★ 서버렌더링 + go_view ID
│   ├─ momstouch_notice.html
│   ├─ bbq_robots.txt / bbq_categories_17.html
│   ├─ bbq_api_menu_category.json              ★ 카테고리 목록
│   ├─ bbq_api_menu_17.json                    ★ 상품 + menuPrice + 영양 + 원산지
│   ├─ bhc_robots.txt                          ★ Content-Signal · ClaudeBot Disallow
│   ├─ bhc_menu_1.html                         카테고리 ID(1,23,47,50,74) 출처
│   ├─ bhc_api_cat23_products.json             ★ REST 응답
│   ├─ bhc_api_categories.json                 404 확인용
│   ├─ kyochon_robots.txt / kyochon_main.html
│   ├─ kyochon_menu_chicken.html               ★ 1요청 69건 + 가격
│   ├─ kyochon_notice.html
│   ├─ dominos_robots.txt / dominos_gate.html / dominos_main.html
│   ├─ dominos_goods_list.html                 ★ EUC-KR 서버렌더링 + code_01 + 가격
│   ├─ dominos_newsList_P.html                 보도자료
│   └─ pizzahut_robots.txt / pizzahut_home.html  404 · SPA 껍데기 근거
```

---

## `sources/targets.yml`에 반영할 사항 (프롬프트 5에서 일괄 처리)

- `mega`: **url을 `https://mega-mgccoffee.com` 으로 수정** (현재 값은 NXDOMAIN)
- `starbucks`, `mcdonalds`, `bbq`, `bhc`, `kyochon`, `dominos`, `momstouch`,
  `parisbaguette`, `baskinrobbins`, `dunkin`, `compose`, `mega` → `status: verified`
- `twosome`, `tourlesjours`, `ediya`, `lotteria` → `status: blocked`
- `burgerking`, `pizzahut` → `status: unverified` 유지 (추가 캡처 필요)
- method: `xhr`(스타벅스·메가·맥도날드·BBQ·bhc·던킨) / `static`(컴포즈·파리바게뜨·
  배스킨라빈스·맘스터치·교촌·도미노) / `playwright`(버거킹·피자헛)
