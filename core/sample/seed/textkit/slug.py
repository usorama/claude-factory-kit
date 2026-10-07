def slug(text):
    """Lower-case words joined by dashes."""
    return "-".join(text.lower().split())
