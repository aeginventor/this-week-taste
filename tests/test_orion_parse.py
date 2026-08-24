"""오리온 목록 파서 골든 테스트 (CLAUDE.md 7장).

`tests/fixtures/orion_list_0101.html`은 2026-08-12에 실제로 받은 파이 카테고리
응답이다. 네트워크 없이 돌고, 오리온이 사이트 구조를 바꿨을 때 무엇이 어떻게
달라졌는지 보여준다.
"""

from pathlib import Path

import pytest

from scrapers import orion

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "orion_list_0101.html"
SCRAPED_AT = "2026-08-12T09:00:00+09:00"


@pytest.fixture(scope="module")
def parsed():
    items, skipped = orion.parse_list(SAMPLE.read_text(encoding="utf-8"), "0101",
                                      scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


def test_파이_카테고리_11건(parsed):
    assert len(parsed) == 11


def test_신제품_배지가_이름에_섞이지_않는다(parsed):
    """`<a>` 전체 텍스트를 쓰면 '신제품오뜨 애플파이'가 된다."""
    names = [i["name"] for i in parsed]
    assert "오뜨 애플파이" in names
    assert not any(n.startswith("신제품") for n in names)


def test_이름이_잘리지_않는다(parsed):
    """CU와 달리 오리온은 POS 접두사도 절삭도 없다. 정찰의 핵심 근거였다."""
    assert "오리온 초코파이情" in [i["name"] for i in parsed]
    assert not any(")" in i["name"][:4] for i in parsed)   # `샐)` 같은 접두사 없음


def test_goodsno가_주키다(parsed):
    first = next(i for i in parsed if i["name"] == "오뜨 애플파이")
    assert first["external_id"] == "175"
    assert first["alt_ids"] == {"goodsno": "175"}


def test_external_id가_카테고리_안에서_유일하다(parsed):
    ids = [i["external_id"] for i in parsed]
    assert len(ids) == len(set(ids))


def test_가격은_항상_없다(parsed):
    """오리온은 브랜드 사이트라 가격을 주지 않는다. 목록에도 상세에도 없다."""
    assert all(i["price"] is None for i in parsed)


def test_이미지_주소를_내보내지_않는다(parsed):
    """오리온은 이미지가 robots.txt 금지 경로(/upload/)에 있다.

    수집은 허용 경로(/goods/list/)만 쓰므로 규칙을 지키지만, 그 주소를 발행하면
    방문자 브라우저가 대신 금지 경로를 요청하게 된다. 그래서 아예 내보내지 않는다.
    원본은 보관되므로(2.5) 판단이 바뀌면 재처리로 되살릴 수 있다.
    """
    assert all(i["image_url"] is None for i in parsed)


def test_카테고리_이름이_들어간다(parsed):
    assert all(i["category_raw"] == "파이" for i in parsed)


def test_신상_라벨은_판정이_아니라_대조군이다(parsed):
    """`_` 접두라 스냅샷 파일에 저장되지 않는다 (CLAUDE.md 2.1)."""
    labelled = [i["name"] for i in parsed if i["_labels"]["new"]]
    assert labelled == ["오뜨 애플파이"]        # 파이 카테고리에서 1건
    assert all(k.startswith("_") or not k.startswith("_") for k in parsed[0])
    assert "_labels" in parsed[0]


def test_source_url이_상세를_가리킨다(parsed):
    first = next(i for i in parsed if i["name"] == "오뜨 애플파이")
    assert first["source_url"] == (
        "https://www.orionworld.com/goods/view/26?goodsno=175&category=0101")


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError):
        orion.parse_list("<html></html>", "9999", scraped_at=SCRAPED_AT)


def test_카테고리_코드와_목록번호가_짝을_이룬다():
    """`category=0201`은 `list/35`에서만 나온다. 짝이 어긋나면 0건이 온다."""
    assert set(orion.CATEGORIES) == set(orion.LIST_IDS)


def test_상세_파싱():
    markup = """
    <html><body>
      <h3>오뜨 애플파이</h3>
      <p>사각사각 씹히는 애플 콩포트가 들어간 데일리 디저트!</p>
      <dl><dt>중량</dt><dd>175g</dd></dl>
    </body></html>
    """
    assert orion.parse_detail(markup) == {
        "name": "오뜨 애플파이",
        "description": "사각사각 씹히는 애플 콩포트가 들어간 데일리 디저트!",
        "tags": [],                 # 오리온에는 태그에 해당하는 것이 없다
    }
