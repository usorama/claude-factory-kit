import pytest


def title(text):
    """Import inside a helper, so this file collects and each test fails on its own until the unit is built."""
    from textkit.title import title_case
    return title_case(text)


def test_each_word_starts_with_a_capital():
    assert title("hello BIG world") == "Hello Big World"


def test_non_text_is_refused():
    with pytest.raises(ValueError, match="text must be a non-blank string"):
        title(None)


def test_blank_text_is_refused():
    with pytest.raises(ValueError, match="text must be a non-blank string"):
        title("   ")
