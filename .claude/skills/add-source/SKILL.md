---
name: add-source
description: 새 수집 소스(마트/편의점/카페/디저트/프랜차이즈/식품사) 하나를 파이프라인에 붙인다. sources/targets.yml 갱신, scrapers/<id>.py 작성, 골든 테스트, pipeline/sources.py 등록까지. "소스 추가", "크롤러 붙이기", "<브랜드> 붙여줘" 같은 요청에 쓴다.
---

# 소스 하나를 붙인다

CLAUDE.md 5장 체크리스트를 실행 순서로 펼친 것이다. **`sources/targets.yml`에
`status: verified`로 대기 중인 소스가 P0만 14개**이므로 이 순서는 최소 14번 반복된다.

원칙은 CLAUDE.md가 갖는다. 여기 적는 것은 **매번 같은 자리에서 걸리는 것들**이다.

---

## 0. 코드를 쓰기 전에 사람에게 묻는다

7장 "실행 전에 승인을 받는 것"이다. 나중에 물으면 이미 요청이 나가 있다.

- **이용약관** — `robots.txt`는 `base.Session`이 강제하지만 약관은 사람이 읽어야 한다
- **이미지 사용 방식** — 원본 CDN 참조가 기본이지만 소스마다 다시 봐야 한다.
  ⚠️ 오리온은 `robots.txt`가 `/upload/`를 막는데 이미지가 거기 있어서 **이미지를 안 내보낸다.**
  같은 경로라도 호스트가 다르면 해당 없다(스타벅스가 그렇다)

`sources/targets.yml`의 해당 항목을 먼저 읽는다. 정찰(1단계) 결과가 이미 거기 있고,
`docs/RECON_*.md`에 더 자세한 실측이 있다. **정찰이 끝난 소스는 다시 정찰하지 않는다.**

## 1. robots.txt를 실측한다

`Crawl-delay`와 `Visit-time`을 본다. 둘 다 있으면 cron에 영향을 준다.

⚠️ **GS25는 `Crawl-delay: 10` + `Visit-time: 0400-0845 UTC`(KST 13:00~17:45)다.**
현재 cron은 KST 월요일 10:00이라 **그 창 밖이다.** 이런 소스는 `make collect-all`에
그냥 태울 수 없다 — 워크플로를 갈라야 한다. 붙이기 전에 사람에게 알린다.

## 2. 전체 카탈로그를 한 번 뜨고 `external_id` 유일성을 실측한다

**추측하지 않는다.** 4장이 경고하는 자리이고, 실제로 바코드가 16건 중복된 적이 있다
([ADR-0001](../../../docs/adr/0001-product-id.md)).

- 주키는 *물리적 제품*이 아니라 **카탈로그 항목**을 가리키는 키로 잡는다
- 소스 간 대조에 쓸 수 있는 키(바코드 등)는 `alt_ids`에 넣는다
- 같은 이름이 두 번 나오는지도 여기서 본다. 나오면 이름 해시로는 가를 수 없다
  (오리온이 동명이인 2건이다)

## 3. 설명문이 어디 있는지 판정한다

`enrich` 경로가 여기서 갈린다. 세 갈래이고 **전부 실제로 있다.**

| 어디 | 소스 | `detail` |
|---|---|---|
| 목록 응답이 이미 준다 | starbucks (326/326) | `False` — 가진 것을 버리고 다시 긁지 않는다 |
| 상세에만 있다 | cu, orion | `True` |
| **상세에도 없다** | homeplus (표본 51건 중 텍스트 1건) | `False` — `blurb`는 항상 `null` |

목록이 주면 스냅샷의 `description`을 채운다(4장). 뒤 두 경우는 `null`이다.
**지어내지 않는다**(6장).

## 4. 파일을 고친다 — 다섯 곳

```
sources/targets.yml       status를 verified로, method·url 확정
scrapers/<id>.py          fetch() + parse_*() + CATEGORIES + BOOTSTRAP_COUNTS
tests/test_<id>_parse.py  tests/fixtures/의 저장된 응답으로 골든 테스트
tests/fixtures/           원본 응답 샘플을 커밋한다 (scratch/는 gitignore라 근거를 못 둔다)
pipeline/sources.py       표에 한 줄: brand·channel·detail·monotonic_key
```

`pipeline/`에서 고칠 곳은 **표 한 줄뿐이다.** 스크래퍼 모듈은 `scrapers/<source_id>.py`
규칙으로 찾으므로 등록이 필요 없다. 카테고리 코드와 부트스트랩 건수는 소스의 *내용*이라
스크래퍼 파일이 갖는다 — `pipeline/`에 두면 7장이 말하는 누수다.

**선례를 그대로 베낀다** (7장: 소스 3개까지 복붙 허용, 4개째에 공통화):

- `scrapers/cu.py` — xhr, 카테고리 7 × 페이지 = 131요청, 상세 있음, `gd_idx` 단조 키
- `scrapers/homeplus.py` — xhr, 카테고리 108개, 가격 있음, 상세에도 설명문 없음
- `scrapers/starbucks.py` — xhr, 목록이 설명문을 준다, 가격 없음
- `scrapers/orion.py` — **static HTML 파싱**, 동명이인 있음, 이미지 미출력

각 스크래퍼는 `fetch(*, week) -> list[dict]` 하나를 노출하고,
`python -m scrapers.<id>`로 단독 실행하면 결과를 stdout에 찍는다.
파싱은 네트워크와 분리한다 — 그래야 골든 테스트가 된다.

`monotonic_key`는 **확인되지 않으면 `None`이다.** 틀린 지표는 없는 지표보다 나쁘다
(7장의 `gd_idx_monotonic` 사고).

## 5. 채널이 dessert / restaurant면 분류 목록을 먼저 만든다

`pipeline/curate.py`의 `CATEGORIES_BY_CHANNEL`에 **그 두 채널이 아직 없다.**
없으면 `system_prompt()`가 예외를 던지고 `curate()`가 LLM을 건너뛰어,
**그 소스 전량이 원본 그대로 발행된다**(조용하다 — 발행은 성공한다).

대기 중인 P0 14개 중 9개가 여기 해당한다:
dessert(parisbaguette, baskinrobbins, dunkin), restaurant(mcdonalds, momstouch, bbq,
bhc, kyochon, dominos).

목록은 **실제 카탈로그를 보고** 만든다([ADR-0006](../../../docs/adr/0006-category-taxonomy-per-channel.md)).
편의점 목록을 재사용하면 분류가 뭉개진다 — 오리온 20건이 전부 `과자`로 떨어져
사이트 필터가 아무 일도 하지 못했던 것이 그 예다.

## 6. 공유 코드가 이 소스의 모양을 견디는지 답한다

5장의 네 질문이다. **테스트는 이미 겪은 것만 지킨다.** 답이 "그렇다"면 그때 테스트를 쓴다.

- `diff.py`가 이 소스의 `alt_ids` 키 이름을 하드코딩하지 않는가
- **가격이 없는 소스인가** — 그러면 diff의 (이름, 가격) 계층이 무력해진다
  (starbucks, orion이 그렇다)
- **같은 이름이 두 번 나오는가** — 이름 해시로 가를 수 없다
- **카테고리가 없는 소스인가** — `snapshot.py`의 건수 검증이 카테고리를 전제한다

## 7. 첫 수집

```bash
make test
THIS_WEEK_TASTE_DATA_DIR=<비공개 데이터 저장소> make snapshot SOURCE=<id>
```

**첫 스냅샷은 발행되지 않는다.** 비교 대상이 없어 구조적으로 불가능하다 —
그래서 8장은 소스 추가를 미루지 말라고 한다. 첫 주는 `BOOTSTRAP_COUNTS` ±10%로
검증되고, 그 다음 주부터 직전 주의 30~300%로 바뀐다([ADR-0002](../../../docs/adr/0002-category-count-baseline.md)).

⚠️ 같은 주차를 다시 뜨려면 `REFRESH=1`이다. 스냅샷이 있으면 다시 긁지 않는다
(2.6, [ADR-0011](../../../docs/adr/0011-snapshot-once-per-week.md)).

## 마지막에 보고한다

- 스스로 정한 것(파서 구현, 파일 배치, 카테고리 코드, 부트스트랩 건수)은 **ADR로 보고**
- 4장 스키마를 건드려야 하면 **먼저 묻는다**(8-1)
- 커밋은 코드와 데이터를 섞지 않는다(9장). 메시지는 커밋 전에 상의한다
