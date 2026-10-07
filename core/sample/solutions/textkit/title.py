def title_case(text):
    """Each word with a capital first letter and the rest lower case."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-blank string")
    return " ".join(word[:1].upper() + word[1:].lower() for word in text.split())
