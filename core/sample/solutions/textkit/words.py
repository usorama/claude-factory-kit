def count_words(text):
    """The number of words in text, split on any whitespace."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return len(text.split())
