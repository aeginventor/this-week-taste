from pipeline.normalize import normalize_name, similarity, split_pos_prefix


def test_collapses_whitespace_and_trims():
    assert normalize_name("  샐)오리지널  닭가슴살 ") == "샐)오리지널 닭가슴살"


def test_nfkc_unifies_width():
    assert normalize_name("ＣＵ　도시락") == normalize_name("CU 도시락")


def test_latin_case_is_unified():
    assert normalize_name("HEYROO 아메리카노") == normalize_name("heyroo 아메리카노")


def test_pos_prefix_is_kept():
    """접두사를 지우면 서로 다른 상품이 병합된다. 실측 근거는 normalize.py 설명 참조."""
    assert normalize_name("삼)치킨마요삼각") != normalize_name("빅삼)치킨마요삼각")
    assert normalize_name("삼)참치마요삼각") != normalize_name("빅삼)참치마요삼각")


def test_split_pos_prefix_is_display_only():
    assert split_pos_prefix("샐)오리지널닭가슴살샐러") == ("샐", "오리지널닭가슴살샐러")
    assert split_pos_prefix("빅삼)치킨마요삼각") == ("빅삼", "치킨마요삼각")
    assert split_pos_prefix("오!그래놀라 저당 카카오") == (None, "오!그래놀라 저당 카카오")


def test_similarity_is_symmetric_and_bounded():
    assert similarity("가나다", "가나다") == 1.0
    assert 0.0 <= similarity("가나다", "라마바") < 1.0
    assert similarity("치킨마요삼각", "치킨마요삼각김밥") == similarity(
        "치킨마요삼각김밥", "치킨마요삼각")


def test_one_character_change_in_a_short_name():
    """CU 이름은 12자에서 잘려서 짧다. 한 글자만 바뀌어도 유사도가 0.917까지 떨어진다.

    diff.SIMILARITY_THRESHOLD를 0.85로 잡은 근거가 이 값이다. 0.92로 두면
    "한 글자 바뀐 12자 이름"조차 L4 후보에 들지 못한다.
    """
    score = similarity(normalize_name("샐)오리지널닭가슴살샐러"),
                       normalize_name("샐)오리지날닭가슴살샐러"))
    assert 0.91 < score < 0.92
    from pipeline.diff import SIMILARITY_THRESHOLD
    assert score >= SIMILARITY_THRESHOLD


def test_two_character_change_falls_below_threshold():
    """두 글자가 바뀌면 더 이상 같은 제품으로 보지 않는다."""
    from pipeline.diff import SIMILARITY_THRESHOLD
    score = similarity(normalize_name("샐)오리지널닭가슴살샐러"),
                       normalize_name("샐)오리지날닭가슴살샐푸"))
    assert score < SIMILARITY_THRESHOLD


# --- User-Agent (CLAUDE.md 5장). 틀리면 익명으로 요청이 나가고 아무 예외도 안 난다.

def test_빈_환경변수는_기본값으로_돌아간다(monkeypatch):
    """CI에서 변수를 정의만 하고 값을 안 채우면 빈 문자열이 온다.

    os.environ.get(키, 기본값)은 그걸 기본값으로 안 바꿔준다.
    """
    import importlib

    monkeypatch.setenv("THIS_WEEK_TASTE_UA", "")
    import scrapers.base as base
    importlib.reload(base)
    try:
        assert base.USER_AGENT == base.DEFAULT_USER_AGENT
    finally:
        monkeypatch.delenv("THIS_WEEK_TASTE_UA", raising=False)
        importlib.reload(base)


def test_빈_UA로는_세션을_못_만든다():
    from scrapers import base
    import pytest as _pytest

    for bad in ("", "   "):
        with _pytest.raises(ValueError, match="비었다"):
            base.Session(user_agent=bad)


def test_UA에_claude를_넣으면_거부한다():
    """일부 사이트가 robots.txt에서 ClaudeBot을 막는다. 넣는 순간 금지 대상이 된다."""
    from scrapers import base
    import pytest as _pytest

    with _pytest.raises(ValueError, match="Claude"):
        base.Session(user_agent="ClaudeBot/1.0")


def test_기본_UA가_실재하는_about_페이지를_가리킨다():
    """UA가 없는 페이지를 가리키면 '연락 가능한 식별자'가 아니다.

    주소는 web/config/site.ts, 페이지는 web/app/about/page.tsx — 셋이 맞아야 한다.
    """
    from pathlib import Path
    from scrapers import base

    assert "example.invalid" not in base.DEFAULT_USER_AGENT
    assert base.DEFAULT_USER_AGENT.endswith("/about)")
    root = Path(__file__).resolve().parent.parent
    assert (root / "web" / "app" / "about" / "page.tsx").exists()

    url = base.DEFAULT_USER_AGENT.split("(+")[1].rstrip(")").removesuffix("/about")
    site_ts = (root / "web" / "config" / "site.ts").read_text(encoding="utf-8")
    assert f'"{url}"' in site_ts, f"site.ts의 url과 UA가 어긋난다: {url}"
