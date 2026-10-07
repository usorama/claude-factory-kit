from textkit.slug import slug


def test_slug_joins_lower_case_words_with_dashes():
    assert slug("Hello Big World") == "hello-big-world"
