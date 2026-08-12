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
