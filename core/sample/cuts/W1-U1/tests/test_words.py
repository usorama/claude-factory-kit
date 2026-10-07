import pytest


def count_words(text):
    """Import inside a helper, so this file collects and each test fails on its own until the unit is built."""
    from textkit.words import count_words as real
    return real(text)


def test_counts_words_separated_by_any_spaces():
    assert count_words("one  two\tthree\nfour") == 4


def test_empty_text_has_zero_words():
    assert count_words("") == 0


def test_non_text_is_refused():
    with pytest.raises(TypeError, match="text must be a string"):
        count_words(42)
